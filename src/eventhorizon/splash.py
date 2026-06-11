"""ASCII splash screen for EventHorizon CLI."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text

from eventhorizon import __version__

BANNER = r"""
  ███████╗██╗   ██╗███████╗███╗   ██╗████████╗
  ██╔════╝██║   ██║██╔════╝████╗  ██║╚══██╔══╝
  █████╗  ██║   ██║█████╗  ██╔██╗ ██║   ██║
  ██╔══╝  ╚██╗ ██╔╝██╔══╝  ██║╚██╗██║   ██║
  ███████╗ ╚████╔╝ ███████╗██║ ╚████║   ██║
  ╚══════╝  ╚═══╝  ╚══════╝╚═╝  ╚═══╝   ╚═╝
  ██╗  ██╗ ██████╗ ██████╗ ██╗███████╗ ██████╗ ███╗   ██╗
  ██║  ██║██╔═══██╗██╔══██╗██║╚══███╔╝██╔═══██╗████╗  ██║
  ███████║██║   ██║██████╔╝██║  ███╔╝ ██║   ██║██╔██╗ ██║
  ██╔══██║██║   ██║██╔══██╗██║ ███╔╝  ██║   ██║██║╚██╗██║
  ██║  ██║╚██████╔╝██║  ██║██║███████╗╚██████╔╝██║ ╚████║
  ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝
"""


def show_splash(console: Console | None = None) -> None:
    """Display the EventHorizon splash screen."""
    if console is None:
        console = Console()

    banner_text = Text(BANNER)
    banner_text.stylize("bold orange3")
    console.print(banner_text)

    console.print(
        f"  [bold white]v{__version__}[/]  [dim]|[/]  "
        "[bold yellow]Drupal Static Analysis CLI[/]  [dim]|[/]  "
        "[dim italic]See beyond your codebase[/]\n"
    )
