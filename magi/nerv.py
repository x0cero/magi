"""The MAGI display: the show's console, drawn in a terminal.

This is deliberately a copy of the reference rather than a reinterpretation of
it. The three units sit in the triangle, wired to a common bus. Status is a
kanji plate, not a word. A decision lands as a solid orange stamp with the
verdict punched out of it in black. Nothing here is subtle, because the thing
being copied is not subtle.

Two constraints shape every helper below:

1. Kanji occupy two terminal cells, Latin one, so every line is padded by
   measured width and never by `len()`. Getting this wrong tears the frame.
2. The panels are drawn as text, not as nested Rich boxes, because the
   diagonal walls and the bus lines between units do not exist in any box set.
"""

from __future__ import annotations

from rich.align import Align
from rich.cells import cell_len
from rich.console import Group
from rich.text import Text

# NERV's palette: black void, one orange that does all the work, red reserved
# for states you are meant to feel, and a bone white for data.
ORANGE = "#ff6a00"
ORANGE_DIM = "#a34400"
RED = "#ff2d16"
GREEN = "#54d658"
BONE = "#e8e2d4"
STEEL = "#5a6672"

# Kanji plates. The council speaks Japanese on the display and English in the
# panels underneath, exactly like the show does with its subtitles.
PLATE_STANDBY = "待 機"
PLATE_READY = "起 動"
PLATE_THINKING = "審 議 中"
PLATE_ACCEPT = "可 決"
PLATE_REJECT = "否 決"
PLATE_CONDITIONAL = "条 件 付"
PLATE_SELECT = "選 択"
PLATE_PROPOSE = "提 案"
PLATE_ERROR = "応 答 な し"

VERDICT_PLATE = {
    "ACCEPT": (PLATE_ACCEPT, GREEN),
    "REJECT": (PLATE_REJECT, RED),
    "CONDITIONAL": (PLATE_CONDITIONAL, ORANGE),
}

UNIT_NUMBER = {"MELCHIOR": "1", "BALTHASAR": "2", "CASPER": "3"}

PANEL_W = 26  # inner width of one unit panel, in terminal cells


def _clip(s: str, width: int) -> str:
    """Cut to a measured cell width, ellipsis included in the budget.

    Needed because a BYOK seat can be named `groq/llama-3.3-70b-versatile`,
    which is wider than a unit panel and used to push the right-hand wall of
    the frame out on that one line.
    """
    if cell_len(s) <= width:
        return s
    if width <= 1:
        return "" if width <= 0 else "…"
    out = ""
    for ch in s:
        if cell_len(out) + cell_len(ch) > width - 1:
            break
        out += ch
    return out + "…"


def _pad(s: str, width: int, align: str = "center") -> str:
    """Pad, or clip, to a measured cell width. Kanji count as two cells."""
    s = _clip(s, width)
    gap = max(0, width - cell_len(s))
    if align == "left":
        return s + " " * gap
    if align == "right":
        return " " * gap + s
    left = gap // 2
    return " " * left + s + " " * (gap - left)


def _unit_lines(name: str, model: str, plate: str, detail: str) -> list[str]:
    """One MAGI unit as a flat-walled hexagon, the shape used on the display."""
    inner = PANEL_W
    title = f"{name} · {UNIT_NUMBER.get(name, '?')}"
    return [
        "  ╱" + "─" * (inner - 4) + "╲  ",
        " ╱ " + _pad(title, inner - 4) + " ╲ ",
        "│" + _pad(plate, inner) + "│",
        "│" + _pad(detail, inner) + "│",
        " ╲ " + _pad(model, inner - 4) + " ╱ ",
        "  ╲" + "─" * (inner - 4) + "╱  ",
    ]


def _blank_lines() -> list[str]:
    return [" " * (PANEL_W + 2)] * 6


class _Cell:
    """A unit's current state, resolved to what the display shows."""

    def __init__(self, name: str, model: str, plate: str, detail: str, color: str):
        self.name = name
        self.model = model
        self.plate = plate
        self.detail = detail
        self.color = color


def _compose(cells: list[_Cell], header_right: str) -> Text:
    """Lay the units out in the show's triangle, wired to a common bus.

    Two on top, one below, joined through a centre node. With more than three
    members (a specialist was invited) the extra units queue on a second row,
    because the triangle is canon and a fourth corner is not.
    """
    top = cells[:2]
    bottom = cells[2:3]
    extra = cells[3:]

    out = Text()
    width = (PANEL_W + 2) * 2 + 6

    def rule(char: str) -> None:
        out.append("┃ ", style=ORANGE_DIM)
        out.append(char * width, style=ORANGE_DIM)
        out.append(" ┃\n", style=ORANGE_DIM)

    # Header bar: the show always states what the screen is and what it is doing.
    out.append("┏" + "━" * (width + 2) + "┓\n", style=ORANGE)
    out.append("┃ ", style=ORANGE)
    left = "MAGI  ·  決 議  ·  CODE:601"
    out.append(_pad(left, width - cell_len(header_right), "left"), style=f"bold {ORANGE}")
    out.append(header_right, style=f"bold {BONE}")
    out.append(" ┃\n", style=ORANGE)
    rule("─")

    def row(units: list[_Cell]) -> None:
        blocks = [_unit_lines(c.name, c.model, c.plate, c.detail) for c in units]
        for i in range(6):
            out.append("┃ ", style=ORANGE_DIM)
            for j, block in enumerate(blocks):
                if j:
                    out.append("  ")
                out.append(block[i], style=units[j].color)
            trailing = width - sum(cell_len(b[i]) for b in blocks) - 2 * (len(blocks) - 1)
            out.append(" " * max(0, trailing))
            out.append(" ┃\n", style=ORANGE_DIM)

    row(top)

    # The bus: both top units drop into one node, which feeds the third.
    # Columns are placed explicitly against the unit centres. Deriving them
    # from panel widths by arithmetic put the junction one cell off the panel
    # it feeds, which is the kind of thing the reference never does.
    block_w = PANEL_W + 2
    left_c = block_w // 2
    right_c = block_w + 2 + block_w // 2
    centre = (width - block_w) // 2 + block_w // 2

    def at(*marks: tuple[int, str]) -> None:
        row_chars = [" "] * width
        for col, ch in marks:
            if 0 <= col < width:
                row_chars[col] = ch
        out.append("┃ ", style=ORANGE_DIM)
        out.append("".join(row_chars), style=ORANGE_DIM)
        out.append(" ┃\n", style=ORANGE_DIM)

    if bottom:
        at((left_c, "│"), (right_c, "│"))
        spine = [(left_c, "└"), (right_c, "┘"), (centre, "┬")]
        spine += [(c, "─") for c in range(left_c + 1, right_c) if c != centre]
        at(*spine)
        at((centre, "│"))

        indent = " " * ((width - block_w) // 2)
        block = _unit_lines(bottom[0].name, bottom[0].model, bottom[0].plate, bottom[0].detail)
        for i in range(6):
            out.append("┃ ", style=ORANGE_DIM)
            out.append(indent)
            out.append(block[i], style=bottom[0].color)
            out.append(" " * max(0, width - cell_len(indent) - cell_len(block[i])))
            out.append(" ┃\n", style=ORANGE_DIM)

    if extra:
        rule("─")
        for start in range(0, len(extra), 2):
            pair = extra[start:start + 2]
            if len(pair) == 1:
                pair = pair + [_Cell("", "", "", "", ORANGE_DIM)]
                blocks = [_unit_lines(pair[0].name, pair[0].model, pair[0].plate, pair[0].detail),
                          _blank_lines()]
                for i in range(6):
                    out.append("┃ ", style=ORANGE_DIM)
                    out.append(blocks[0][i], style=pair[0].color)
                    out.append("  ")
                    out.append(blocks[1][i])
                    out.append(" " * max(0, width - cell_len(blocks[0][i]) - cell_len(blocks[1][i]) - 2))
                    out.append(" ┃\n", style=ORANGE_DIM)
            else:
                row(pair)

    out.append("┗" + "━" * (width + 2) + "┛", style=ORANGE)
    return out


def _cell_for(name: str, model: str, result, phase_plate: str, mode: str) -> _Cell:
    """Resolve one member's live state into a plate and a one-line detail."""
    short = model.split("/")[-1]
    if result is None:
        return _Cell(name, short, phase_plate, "· · ·", ORANGE_DIM)
    if isinstance(result, Exception):
        return _Cell(name, short, PLATE_ERROR, type(result).__name__[:22], RED)

    if mode == "boot":
        # Warmup has no verdict to show: a seat is either holding or up.
        return _Cell(name, short, PLATE_READY, "READY", ORANGE)

    verdict = getattr(result, "verdict", None) or getattr(result, "final_verdict", None)
    if verdict is not None:
        plate, color = VERDICT_PLATE.get(getattr(verdict, "name", ""), (PLATE_THINKING, ORANGE))
        return _Cell(name, short, plate, getattr(verdict, "value", ""), color)

    pick = (getattr(result, "chosen_option", None) or getattr(result, "final_choice", None)
            or getattr(result, "recommendation", None))
    if pick:
        plate = PLATE_SELECT if mode != "recommend" else PLATE_PROPOSE
        return _Cell(name, short, plate, str(pick)[:PANEL_W - 2], ORANGE)
    return _Cell(name, short, phase_plate, "· · ·", ORANGE_DIM)


def magi_display(
    models: dict[str, str],
    results: dict,
    header: str = "審 議 中",
    phase_plate: str = PLATE_THINKING,
    mode: str = "decision",
) -> Text:
    """The live console. Called on every event, so it must stay cheap."""
    order = [n for n in ("MELCHIOR", "BALTHASAR", "CASPER") if n in models]
    order += [n for n in models if n not in order]
    cells = [_cell_for(n, models[n], results.get(n), phase_plate, mode) for n in order]
    return _compose(cells, header)


def stamp(headline: str, plate: str, color: str, sub: str = "") -> Group:
    """The verdict, punched out of a solid plate.

    Reverse video is doing the work: on the display a decision is not coloured
    text, it is a filled panel with the characters cut out of it.
    """
    width = (PANEL_W + 2) * 2 + 6  # the stamp is exactly as wide as the console
    lines = []
    bar = Text()
    bar.append(_pad("", width), style=f"on {color}")
    lines.append(Align.center(bar))

    plate_line = Text()
    plate_line.append(_pad(plate, width), style=f"bold black on {color}")
    lines.append(Align.center(plate_line))

    # A synthesis line can carry a trailing clause explaining how a tie broke.
    # That belongs under the plate as a caption rather than clipped off the end
    # of the verdict. The clause is separated by a wide interpunct, while the
    # tally inside the verdict uses a narrow one, so this split is unambiguous.
    verdict, _, caption = headline.partition("  ·  ")
    # The display separates with interpuncts and spacing, never with a dash.
    verdict = verdict.upper().replace(" — ", "  ·  ").replace(" - ", "  ·  ")

    head = Text()
    head.append(_pad(verdict, width), style=f"bold black on {color}")
    lines.append(Align.center(head))

    lines.append(Align.center(bar))
    if sub:
        tail = Text()
        tail.append(_pad(sub, width), style=STEEL)
        lines.append(Align.center(tail))
    if caption:
        note = Text()
        note.append(_pad(caption, width), style=STEEL)
        lines.append(Align.center(note))
    return Group(*lines)


BOOT_LINES = [
    ("NERV", "MAGI SYSTEM  ·  PERSONALITY TRANSPLANT OS"),
    ("BUS", "MELCHIOR-1  BALTHASAR-2  CASPER-3  ·  LINKED"),
    ("MODE", "DELIBERATION  ·  MAJORITY CARRIES  ·  NO ABSTENTION"),
]


def boot(models: dict[str, str], version: str) -> Group:
    """Startup. Says what the machine is and what rule it decides by."""
    out: list = []
    title = Text()
    title.append(_pad("M A G I", 60), style=f"bold black on {ORANGE}")
    out.append(Align.center(title))
    sub = Text()
    sub.append(_pad(f"決 議 SYSTEM  ·  v{version}", 60), style=f"black on {ORANGE_DIM}")
    out.append(Align.center(sub))
    out.append(Text())
    for tag, line in BOOT_LINES:
        t = Text("  ")
        t.append(f"{tag:<6}", style=f"bold {ORANGE}")
        t.append(line, style=BONE)
        out.append(t)
    seats = Text("  ")
    seats.append(f"{'SEATS':<6}", style=f"bold {ORANGE}")
    for i, name in enumerate(("MELCHIOR", "BALTHASAR", "CASPER")):
        if name not in models:
            continue
        if i:
            seats.append("  ·  ", style=STEEL)
        seats.append(f"{name}-{UNIT_NUMBER[name]}", style=f"bold {ORANGE}")
        seats.append(f" {models[name].split('/')[-1]}", style=STEEL)
    out.append(seats)
    return Group(*out)
