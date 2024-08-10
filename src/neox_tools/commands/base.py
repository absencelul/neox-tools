from abc import ABC, abstractmethod
import click


class Command(ABC):
    @abstractmethod
    def create(self) -> click.Command:
        pass
