"""Ergos CLI interface."""

import asyncio
import faulthandler
import logging
import sys
from pathlib import Path

# Enable faulthandler to get stack traces on segfaults
faulthandler.enable()

import click

from ergos.config import Config, load_config, save_config
from ergos.hardware import detect_hardware, log_hardware_info
from ergos.server import Server


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity.

    In normal mode: ergos logs at INFO, third-party libs at WARNING.
    In verbose mode: ergos logs at DEBUG, third-party libs at INFO.
    """
    # Set ergos level based on verbosity
    ergos_level = logging.DEBUG if verbose else logging.INFO
    # Keep third-party libs quieter
    third_party_level = logging.INFO if verbose else logging.WARNING

    logging.basicConfig(
        level=ergos_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # Silence noisy third-party loggers
    for lib in ["aiortc", "aioice", "av", "PIL", "urllib3", "httpx", "httpcore", "faster_whisper"]:
        logging.getLogger(lib).setLevel(third_party_level)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.version_option()
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Ergos - Local-first voice assistant.

    A privacy-focused voice assistant that runs entirely on your hardware.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(),
    default="config.yaml",
    help="Path to configuration file",
)
@click.pass_context
def start(ctx: click.Context, config_path: str) -> None:
    """Start the Ergos server."""
    logger = logging.getLogger(__name__)

    # Check if already running
    status = Server.get_status()
    if status["state"] == "running":
        click.echo(f"Server already running (PID: {status['pid']})")
        sys.exit(1)

    # Load configuration
    config = load_config(config_path)
    logger.info(f"Loaded configuration from {config_path}")

    # Detect and log hardware
    hardware = detect_hardware()
    log_hardware_info(hardware)

    # Start server
    server = Server(config)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        click.echo("\nShutdown requested")


@main.command()
def stop() -> None:
    """Stop the Ergos server."""
    status = Server.get_status()

    if status["state"] == "stopped":
        click.echo("Server is not running")
        return

    if Server.send_stop_signal():
        click.echo(f"Stop signal sent to server (PID: {status['pid']})")
    else:
        click.echo("Failed to stop server")
        sys.exit(1)


@main.command()
def status() -> None:
    """Show server status."""
    server_status = Server.get_status()

    if server_status["state"] == "running":
        click.echo(f"Server is running (PID: {server_status['pid']})")
    else:
        click.echo("Server is stopped")


@main.command()
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default="config.yaml",
    help="Output path for configuration file",
)
def setup(output: str) -> None:
    """Create default configuration file."""
    path = Path(output)
    if path.exists():
        if not click.confirm(f"{output} already exists. Overwrite?"):
            click.echo("Aborted")
            return

    config = Config()
    save_config(config, path)
    click.echo(f"Configuration saved to {output}")

    # Show hardware info
    click.echo("\nDetected hardware:")
    hardware = detect_hardware()
    click.echo(f"  Platform: {hardware.platform}")
    click.echo(f"  Python: {hardware.python_version}")
    if hardware.gpu.available:
        click.echo(f"  GPU: {hardware.gpu.name} ({hardware.gpu.memory_gb}GB)")
    else:
        click.echo("  GPU: Not available (will use CPU)")
    click.echo(f"  Recommended device: {hardware.recommended_device}")


if __name__ == "__main__":
    main()
