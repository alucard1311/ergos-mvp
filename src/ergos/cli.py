"""Ergos CLI interface."""

import click


@click.group()
@click.version_option()
def main() -> None:
    """Ergos - Local-first voice assistant."""
    pass


@main.command()
def status() -> None:
    """Show server status."""
    click.echo("Ergos is not running")


if __name__ == "__main__":
    main()
