"""
app/data_sources/interfaces/base_source.py
==========================================

Description
-----------
Définition de la classe abstraite BaseSource.

BaseSource constitue le contrat commun de toutes les sources
de données du projet GMAO AI Service.

Toutes les implémentations (FileSource, MySQLSource, APISource,
etc.) héritent de cette classe.

Responsabilités
---------------
- Validation de la source
- Gestion du cycle de vie
- Gestion des connexions
- Gestion des ressources
- Logging
- Context Manager
- Interface commune

Cette classe utilise le Template Method Pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from logging import Logger, getLogger
from threading import RLock
from typing import Generic, TypeVar

from app.exceptions import (
    CloseError,
    DataConnectionError,
    LoadingError,
    ValidationError,
)
from app.models.document import SourceDocument

# ==========================================================
# Generic Type
# ==========================================================

T = TypeVar("T")


class SourceState(Enum):
    INITIALIZED = "initialized"
    CONNECTED = "connected"
    CLOSED = "closed"
    ERROR = "error"


# ==========================================================
# Base Class
# ==========================================================

class BaseSource(ABC, Generic[T]):
    """
    Classe abstraite représentant une source de données.

    Toutes les sources de données du projet doivent hériter
    de cette classe.

    Examples
    --------
    >>> loader = PDFLoader("manual.pdf")
    >>> document = loader.read()

    ou

    >>> with PDFLoader("manual.pdf") as loader:
    ...     document = loader.read()
    """

    # ======================================================
    # Constructor
    # ======================================================

    def __init__(
        self,
        source: T,
    ) -> None:
        """
        Initialise une nouvelle source.

        Parameters
        ----------
        source:
            Objet représentant la source.
            (Path, connexion MySQL, URL, etc.)
        """

        self._source = source

        self._state = SourceState.INITIALIZED
        self._lock = RLock()
        self._connect_lock = RLock()
        self._close_lock = RLock()

        self._logger: Logger = getLogger(
            self.__class__.__name__
        )

    # ======================================================
    # Properties
    # ======================================================

    @property
    def source(self) -> T:
        """
        Retourne la source.
        """
        return self._source

    @property
    def logger(self) -> Logger:
        """
        Logger associé à la source.
        """
        return self._logger

    @property
    def state(self) -> SourceState:
        """
        Retourne l'état courant de la source.
        """
        return self._state

    @property
    def is_connected(self) -> bool:
        """
        Indique si la source est connectée.
        """
        with self._lock:
            return self._state is SourceState.CONNECTED

    @property
    def is_closed(self) -> bool:
        """
        Indique si la ressource est fermée.
        """
        with self._lock:
            return self._state is SourceState.CLOSED

    @property
    def is_error(self) -> bool:
        """
        Indique si la source est dans un état d'erreur.
        """
        with self._lock:
            return self._state is SourceState.ERROR

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Nom lisible de la source."""
        raise NotImplementedError
    
    # ======================================================
    # Protected Helpers
    # ======================================================

    def _set_state(self, state: SourceState) -> None:
        """
        Met à jour l'état global de la source.

        Cette méthode est réservée aux classes dérivées.
        """
        with self._lock:
            self._state = state

    def _connect_with_state(self) -> None:
        """
        Établit une connexion de manière sûre et idempotente.

        Un verrou dédié encapsule la séquence complète
        (vérification d'état, appel à _connect() et mise à jour
        d'état) afin d'éviter une race condition entre threads.
        """
        with self._connect_lock:
            with self._lock:
                if self._state is SourceState.CONNECTED:
                    return
                if self._state is SourceState.CLOSED:
                    raise DataConnectionError(
                        f"{self.__class__.__name__} is already closed."
                    )
                if self._state is SourceState.ERROR:
                    raise DataConnectionError(
                        f"{self.__class__.__name__} is in an error state."
                    )

            try:
                self._connect()
            except ValidationError:
                self._set_state(SourceState.ERROR)
                raise
            except DataConnectionError:
                self._set_state(SourceState.ERROR)
                raise
            except CloseError:
                self._set_state(SourceState.ERROR)
                raise
            except Exception as exc:
                self._set_state(SourceState.ERROR)
                raise DataConnectionError(
                    f"Unable to connect to {self.source_name}."
                ).with_original(exc) from exc

            self._set_state(SourceState.CONNECTED)

    def _close_with_state(self) -> None:
        """
        Ferme la ressource de manière idempotente.

        Un verrou dédié garantit qu'une seule opération de fermeture
        peut être exécutée à la fois, même si plusieurs threads
        appellent cette méthode simultanément.
        """
        with self._close_lock:
            with self._lock:
                if self._state is SourceState.CLOSED:
                    return

            try:
                self._close()
            except CloseError:
                self._set_state(SourceState.ERROR)
                raise
            except ValidationError:
                self._set_state(SourceState.ERROR)
                raise
            except Exception as exc:
                self._set_state(SourceState.ERROR)
                raise CloseError(
                    f"Unable to close {self.source_name}."
                ).with_original(exc) from exc

            self._set_state(SourceState.CLOSED)

    def connect(self) -> None:
        """Établit la connexion manuellement."""
        self._connect_with_state()

    def close(self) -> None:
        """Ferme la ressource manuellement."""
        self._close_with_state()

    # ======================================================
    # Context Manager
    # ======================================================

    def __enter__(self) -> "BaseSource[T]":
        """
        Active le Context Manager.

        Returns
        -------
        BaseSource
        """
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        """
        Libère automatiquement les ressources.

        Returns
        -------
        bool
            False pour propager les exceptions.
        """
        self.close()
        return False

    # ======================================================
    # Abstract API
    # ======================================================

    @abstractmethod
    def validate(self) -> None:
        """
        Vérifie que la source est valide.
        """
        raise NotImplementedError

    @abstractmethod
    def _connect(self) -> None:
        """
        Ouvre la connexion avec la source.
        """
        raise NotImplementedError

    @abstractmethod
    def load(self) -> SourceDocument:
        """
        Charge les données.

        Returns
        -------
        SourceDocument
        """
        raise NotImplementedError

    @abstractmethod
    def _close(self) -> None:
        """
        Libère toutes les ressources utilisées.
        """
        raise NotImplementedError

    # ======================================================
    # Public API
    # ======================================================

    def read(self) -> SourceDocument:
        """
        Lit la source de données en exécutant automatiquement
        toutes les étapes du cycle de vie.

        Workflow
        --------
        1. Validation
        2. Connexion
        3. Chargement
        4. Fermeture

        Returns
        -------
        SourceDocument
            Document chargé depuis la source.

        Raises
        ------
        ValidationError
            Si la source est invalide.

        DataConnectionError
            Si la connexion échoue.

        LoadingError
            Si le chargement échoue.

        CloseError
            Si la fermeture échoue.
        """

        self.logger.info(
            "Starting data loading from '%s'.",
            self.source_name,
        )

        raised = False

        try:
            self.logger.debug("Validating source...")
            self.validate()

            self.logger.debug("Connecting to source...")
            self._connect_with_state()

            self.logger.debug("Loading data...")
            document = self.load()

            self.logger.info(
                "Successfully loaded '%s'.",
                self.source_name,
            )

            return document

        except ValidationError as exc:
            raised = True
            self._set_state(SourceState.ERROR)
            self.logger.exception(
                "Validation failed for '%s'.",
                self.source_name,
            )
            raise exc

        except DataConnectionError as exc:
            raised = True
            self._set_state(SourceState.ERROR)
            self.logger.exception(
                "Connection failed for '%s'.",
                self.source_name,
            )
            raise exc

        except LoadingError as exc:
            raised = True
            self._set_state(SourceState.ERROR)
            self.logger.exception(
                "Loading failed for '%s'.",
                self.source_name,
            )
            raise exc

        except Exception as exc:
            raised = True
            self._set_state(SourceState.ERROR)
            wrapped = LoadingError(
                f"Unexpected error while reading '{self.source_name}'."
            ).with_original(exc)
            self.logger.exception(
                "Unexpected error while reading '%s'.",
                self.source_name,
            )
            raise wrapped from exc

        finally:
            try:
                self._close_with_state()

            except CloseError as exc:
                self.logger.exception(
                    "Unable to close '%s'.",
                    self.source_name,
                )
                if not raised:
                    raise exc

            except Exception as exc:
                self.logger.exception(
                    "Unable to close '%s'.",
                    self.source_name,
                )
                if not raised:
                    raise CloseError(
                        f"Unable to close '{self.source_name}'."
                    ).with_original(exc) from exc

    # ======================================================
    # State Helpers
    # ======================================================

    def ensure_connected(self) -> None:
        """
        Vérifie que la source est connectée.

        Raises
        ------
        DataConnectionError
            Si la source n'est pas connectée.
        """

        if not self.is_connected:
            raise DataConnectionError(
                f"{self.__class__.__name__} is not connected."
            )

    def ensure_open(self) -> None:
        """
        Vérifie que la ressource n'est pas fermée.

        Raises
        ------
        DataConnectionError
            Si la ressource est déjà fermée.
        """

        if self.is_closed or self.is_error:
            raise DataConnectionError(
                f"{self.__class__.__name__} is already closed or in error state."
            )

    # ======================================================
    # Convenience Methods
    # ======================================================

    def __repr__(self) -> str:
        """
        Représentation utilisée pour le débogage.
        """

        return (
            f"{self.__class__.__name__}("
            f"source={self.source_name!r}, "
            f"state={self.state.value}, "
            f"connected={self.is_connected}, "
            f"closed={self.is_closed}, "
            f"error={self.is_error})"
        )

    def __str__(self) -> str:
        """
        Représentation lisible de la source.
        """

        return self.source_name

    # ======================================================
    # Lifecycle Helpers
    # ======================================================

    def reset(self) -> None:
        """
        Réinitialise l'état interne de la source.

        Cette méthode permet de réutiliser une même instance
        après sa fermeture si l'implémentation le permet.
        Avant de repasser à l'état INITIALIZED, la ressource
        sous-jacente est fermée si nécessaire via _close_with_state().
        """

        if not self.is_closed:
            self._close_with_state()

        with self._lock:
            self._state = SourceState.INITIALIZED
            self.logger.debug(
                "Source '%s' has been reset.",
                self.source_name,
            )

    # ======================================================
    # Status Helpers
    # ======================================================

    @property
    def is_ready(self) -> bool:
        """
        Indique si la source est prête à être utilisée.
        """

        return (
            not self.is_closed
            and self.is_connected
        )

    @property
    def status(self) -> str:
        """
        Retourne l'état courant de la source.
        """

        if self.is_closed:
            return "closed"

        if self.is_connected:
            return "connected"

        return "disconnected"

    # ======================================================
    # Equality
    # ======================================================

    def __eq__(
        self,
        other: object,
    ) -> bool:
        """
        Compare deux sources.
        """

        # La comparaison repose sur hash(self.source) ; les sous-classes
        # doivent donc fournir une valeur de source hashable.

        if not isinstance(other, BaseSource):
            return NotImplemented

        return self.source == other.source

    def __hash__(self) -> int:
        """
        Retourne le hash de la source.
        """

        return hash(self.source)

    # ======================================================
    # Destructor
    # ======================================================

    def __del__(self) -> None:
        """
        Libère les ressources restantes.

        Cette méthode n'est pas la voie principale de nettoyage ;
        le context manager ou l'appel explicite à close() reste
        recommandé pour une fermeture maîtrisée.
        """

        try:
            required_attrs = ("_lock", "_close_lock", "_logger")
            if not all(hasattr(self, attr) for attr in required_attrs):
                return
            self._close_with_state()
        except Exception:
            pass