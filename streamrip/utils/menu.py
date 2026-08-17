"""The scrolling multi-select menu used for anything the user has to pick from.

`rip search` grew this first; artist downloads need exactly the same thing, so
it lives here rather than being written twice with the Windows fallback only
handled in one of them.
"""

import platform

from ..console import console


def multi_select(
    entries: list[str],
    title: str,
    previews: list[str] | None = None,
) -> list[int]:
    """Show `entries` and return the indices the user chose.

    Empty if they chose nothing or backed out. `previews`, when given, must be
    the same length as `entries`.
    """
    if not entries:
        return []

    if platform.system() == "Windows":
        # simple-term-menu is unix only.
        from pick import pick

        chosen = pick(entries, title=title, multiselect=True, min_selection_count=0)
        if not chosen:
            return []
        return [index for _, index in chosen]

    from simple_term_menu import TerminalMenu

    preview_command = None
    if previews:
        by_entry = dict(zip(entries, previews))

        def preview_command(entry: str) -> str:  # noqa: F811
            return by_entry.get(entry, "")

    menu = TerminalMenu(
        entries,
        title=title,
        preview_command=preview_command,
        preview_size=0.4,
        cycle_cursor=True,
        clear_screen=True,
        multi_select=True,
        show_multi_select_hint=True,
    )
    chosen = menu.show()
    if chosen is None:
        return []
    if isinstance(chosen, int):
        return [chosen]
    return list(chosen)


def announce_nothing_chosen() -> None:
    console.print("[yellow]No items chosen. Exiting.")
