import os
import time
from pathlib import Path

import click

from neox_tools.core.extractor import (
    process_single_npk_file,
    process_multiple_npk_files,
)
from neox_tools.commands.base import Command


class ExtractCommand(Command):
    def create(self) -> click.Command:
        @click.command()
        @click.argument("path", type=click.Path(exists=True))
        @click.option(
            "--output-dir",
            "-o",
            type=click.Path(),
            help="Output directory for extracted files",
        )
        @click.option("--no-nxfn", is_flag=True, help="Disable NXFN file structuring")
        @click.option(
            "--delete-compressed",
            is_flag=True,
            help="Delete compressed archives within the NPK file",
        )
        def extract(
            path: str,
            output_dir: str,
            no_nxfn: bool,
            delete_compressed: bool,
        ):
            """Extract NPK Files."""
            start_time = time.time()

            path = Path(path)
            output_dir = Path(output_dir) if output_dir else path.with_suffix("")

            if path.is_dir():
                process_multiple_npk_files(
                    npk_files=list(path.glob("*.npk")),
                    output_dir=output_dir,
                    no_nxfn=no_nxfn,
                    delete_compressed=delete_compressed,
                    max_workers=os.cpu_count(),
                )
            else:
                if path.suffix.lower() == ".npk":
                    process_single_npk_file(
                        npk_file=path,
                        output_dir=output_dir,
                        no_nxfn=no_nxfn,
                        delete_compressed=delete_compressed,
                        max_workers=os.cpu_count(),
                    )
                else:
                    click.echo(f"Error: The file {path} is not an NPK file.")

            click.echo("Extraction completed successfully.")

            # End timing the function
            end_time = time.time()
            duration = end_time - start_time
            click.echo(f"Function 'extract' executed in {duration:.2f} seconds.")

        return extract
