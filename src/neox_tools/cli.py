from typing import List

import click

from .commands.base import Command
from .commands import extract


class Cli:
    def __init__(self) -> None:
        self.commands: List[Command] = [
            extract.ExtractCommand(),
        ]

    def create(self) -> click.Group:
        @click.group()
        def cli() -> None:
            """NeoX Tools"""
            pass

        for command in self.commands:
            cli.add_command(command.create())

        return cli


def main():
    cli = Cli().create()
    cli()
