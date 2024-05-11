"""
lfcircle: last.fm statistics generator for your friend circle!
--------------------------------------------------------------
with all my heart, from me to you
mark <mark@joshwel.co>, 2024

This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <http://unlicense.org/>
"""

from argparse import ArgumentParser
from bisect import insort
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from sys import stderr
from textwrap import indent
from time import sleep
from traceback import format_exception
from typing import Callable, Final, NamedTuple, ParamSpec, TypeVar
from urllib.parse import unquote

from bs4 import BeautifulSoup
from requests import Response, get

FORMAT_TELEGRAM_PREFIX: Final[str] = "   "
USER_AGENT: Final[str] = (
    "Mozilla/5.0 " "(compatible; lfcircle; https://github.com/markjoshwel/lfcircle)"
)


class FormatTypeEnum(Enum):
    """
    enum for what kind of formatting the results are to be shown in

    - `ASCII`: readable ascii that could also work as markdown
    - `TELEGRAM`: a weird amalgam of markdown and plaintext
    """

    ASCII = "ascii"
    TELEGRAM = "telegram"


class Behaviour(NamedTuple):
    """
    data structure dictating the operation of lfcircle
    
    - `targets: list[str] = []` \\
      users to target
    
    - `header: str = ""` \\
      specify a report header, leave empty for none
    
    - `truncate_scheme: bool = False` \\
      removes 'https://' in any links

    - `lowercase: bool = False` \\
      makes everything lowercase

    - `all_the_links: bool = False` \\
      adds links for top artists, albums and tracks

    - `format: FormatTypeEnum = FormatTypeEnum.ASCII` \\
      what format to output, see FormatTypeEnum
    
    - `verbose: bool = False` \\
      enable verbose logging
    """

    targets: list[str] = []
    header: str = ""
    truncate_scheme: bool = False
    lowercase: bool = False
    all_the_links: bool = False
    format: FormatTypeEnum = FormatTypeEnum.ASCII
    verbose: bool = False


def handle_args() -> Behaviour:
    """helper function to handle cli args"""
    info = __doc__.strip().split("\n", maxsplit=1)[0].split(":", maxsplit=1)
    default_behaviour = Behaviour()

    parser = ArgumentParser(
        prog=info[0].strip(),
        description=info[-1].strip(),
    )

    parser.add_argument(
        "targets",
        nargs="*",
        type=str,
        help="users to target",
    )
    parser.add_argument(
        "-H",
        "--header",
        type=str,
        help="specify a report header, leave empty for none",
        default=default_behaviour.header,
    )
    parser.add_argument(
        "-t",
        "--truncate-scheme",
        action="store_true",
        help="removes 'https://www.' in any links",
        default=default_behaviour.truncate_scheme,
    )
    parser.add_argument(
        "-l",
        "--lowercase",
        action="store_true",
        help="makes everything lowercase",
        default=default_behaviour.lowercase,
    )
    parser.add_argument(
        "-a",
        "--all-the-links",
        action="store_true",
        help="adds links for top artists, albums and tracks",
        default=default_behaviour.all_the_links,
    )
    parser.add_argument(
        "-f",
        "--format",
        type=str,
        help="output format type",
        choices=[v.value for v in FormatTypeEnum],
        default=default_behaviour.format,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose logging",
    )

    args = parser.parse_args()
    return Behaviour(
        targets=args.targets,
        header=args.header,
        truncate_scheme=args.truncate_scheme,
        lowercase=args.lowercase,
        all_the_links=args.all_the_links,
        format=FormatTypeEnum(args.format),
        verbose=args.verbose,
    )


P = ParamSpec("P")
R = TypeVar("R")


class Limiter:
    """helper to class to not bomb last.hq"""

    max_per_second: int = 1
    last_call: datetime | None = None

    def limit(
        self, func: Callable[P, R], sleeper: Callable[[float], None] = sleep
    ) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs):
            if self.last_call is None:
                self.last_call = datetime.now()
                return func(*args, **kwargs)

            while (self.last_call + timedelta(seconds=1)) > (now := datetime.now()):
                sleeper(1)

            self.last_call = now
            return func(*args, **kwargs)

        return wrapper


class ThingWithScrobbles(NamedTuple):
    """shared data structure for artists, albums and tracks"""

    name: str = ""
    scrobbles: int = 0
    url: str | None = None


def _qualified_thing_name(thing: ThingWithScrobbles) -> str:
    """use the url of a 'thing' to get a more qualified name"""

    if thing.url is None:
        return thing.name

    right = thing.name
    left = (
        unquote(thing.url)
        .lstrip("https://www.last.fm/music/")
        .replace("+", " ")
        .split("/", maxsplit=1)
    )

    return right if (len(left) == 0) else f"{left[0]} — {right}"


class ListeningReport(NamedTuple):
    """data structure representing a last.fm listening report"""

    user: str
    url: str
    scrobbles_count: int
    scrobbles_daily_avg: int
    artists_count: int
    albums_count: int
    tracks_count: int
    artists: tuple[ThingWithScrobbles, ...]
    albums: tuple[ThingWithScrobbles, ...]
    tracks: tuple[ThingWithScrobbles, ...]
    artists_top_new: ThingWithScrobbles
    albums_top_new: ThingWithScrobbles
    tracks_top_new: ThingWithScrobbles
    listening_time_hours: int

    def to_str(
        self,
        behaviour: Behaviour,
        leaderboard_pos: int,
        leaderboard_scrobble_pos: int,
        leaderboard_artists_pos: int,
        leaderboard_albums_pos: int,
        leaderboard_tracks_pos: int,
        leaderboard_n: int,
    ) -> str:
        basket: list[str] = []
        prefix: str = ""
        text: str = ""

        match behaviour.format:
            case FormatTypeEnum.ASCII:
                # intro
                basket.append(
                    (_prefix := f"{leaderboard_pos}. ")
                    + f"{self.user} — Σ{self.listening_time_hours}h; {self.scrobbles_daily_avg}s/d  "
                )
                basket.append(
                    indent(f"<{self.url}>", prefix=(prefix := " " * len(_prefix))) + "\n"
                )

                rmax = len(f"#{leaderboard_n}")

                # detail 1: total period scrobble count
                d1_l = indent(ls := f"{self.scrobbles_count} scrobbles", prefix=prefix)
                d1_r = " (" + f"#{leaderboard_scrobble_pos}".rjust(rmax) + ")"
                basket.append(d1_l + d1_r)

                # detail 2: total period artist count
                d2_l = indent(
                    f"{self.artists_count} artists".ljust(len(ls))
                    + " ("
                    + f"#{leaderboard_artists_pos}".rjust(rmax)
                    + ") : ",
                    prefix=prefix,
                )
                d2_r = self.artists[0].name
                d2_url = (
                    ("\n" + indent(f"<{self.artists[0].url}>", prefix=" " * len(d2_l)))
                    if behaviour.all_the_links
                    else ""
                )
                basket.append(d2_l + d2_r + d2_url)

                # detail 3: total period album count
                d3_l = indent(
                    f"{self.albums_count} albums".ljust(len(ls))
                    + " ("
                    + f"#{leaderboard_albums_pos}".rjust(rmax)
                    + ") : ",
                    prefix=prefix,
                )
                d3_r = _qualified_thing_name(self.albums[0])
                d3_url = (
                    ("\n" + indent(f"<{self.albums[0].url}>", prefix=" " * len(d2_l)))
                    if behaviour.all_the_links
                    else ""
                )
                basket.append(d3_l + d3_r + d3_url)

                # detail 4: total period tracks count
                d4_l = indent(
                    f"{self.tracks_count} tracks".ljust(len(ls))
                    + " ("
                    + f"#{leaderboard_tracks_pos}".rjust(rmax)
                    + ") : ",
                    prefix=prefix,
                )
                d4_r = _qualified_thing_name(self.tracks[0])
                d4_url = (
                    ("\n" + indent(f"<{self.tracks[0].url}>", prefix=" " * len(d2_l)))
                    if behaviour.all_the_links
                    else ""
                )
                basket.append(d4_l + d4_r + d4_url)

                if not behaviour.lowercase:
                    text = "\n".join(basket)

                else:
                    text = "\n".join(basket[:3] + [s.lower() for s in basket[3:]])

            case FormatTypeEnum.TELEGRAM:
                prefix = FORMAT_TELEGRAM_PREFIX

                # intro
                basket.append(
                    f"{leaderboard_pos}. [{self.user}]({self.url}) "
                    f"— Σ{self.listening_time_hours}h; {self.scrobbles_daily_avg}s/d  "
                )

                # detail 1: total period scrobble count
                basket.append(f"{prefix}**{self.scrobbles_count} scrobbles**")

                # detail 2: total period artist count
                basket.append(
                    f"{prefix}{self.artists_count} artists (#{leaderboard_artists_pos}): "
                    + (
                        f"[{self.artists[0].name}]({self.artists[0].url})"
                        if behaviour.all_the_links
                        else self.artists[0].name
                    )
                )

                # detail 3: total period album count
                _qual_album_name = _qualified_thing_name(self.albums[0])
                basket.append(
                    f"{prefix}{self.albums_count} albums (#{leaderboard_albums_pos}): "
                    + (
                        f"[{_qual_album_name}]({self.albums[0].url})"
                        if behaviour.all_the_links
                        else _qual_album_name
                    )
                )

                # detail 4: total period tracks count
                _qual_track_name = _qualified_thing_name(self.tracks[0])
                basket.append(
                    f"{prefix}{self.tracks_count} tracks (#{leaderboard_tracks_pos}): "
                    + (
                        f"[{_qual_track_name}]({self.tracks[0].url})"
                        if behaviour.all_the_links
                        else _qual_track_name
                    )
                )

                if not behaviour.lowercase:
                    text = "\n".join(basket)

                else:
                    text = "\n".join(basket[:1] + [s.lower() for s in basket[1:]])

            case _:
                raise NotImplementedError(
                    f"unexpected behaviour format '{behaviour.format}'"
                )

        if behaviour.truncate_scheme:
            text = text.replace("https://www.", "")

        return text


def get_listening_report(
    target: str,
    limiter: Limiter,
    behaviour: Behaviour,
) -> ListeningReport:

    target_url: str = f"https://www.last.fm/user/{target}/listening-report/week"

    page_res: Response = limiter.limit(get)(
        target_url,
        headers={"User-Agent": USER_AGENT},
    )

    if page_res.status_code != 200:
        raise Exception(
            f"non-nominal status code {page_res.status_code} for '{target_url}'"
        )

    page = BeautifulSoup(page_res.text, "html5lib")

    return ListeningReport(
        user=target,
        url=target_url,
        scrobbles_count=_get_scrobbles_count(page),
        scrobbles_daily_avg=_get_scrobbles_daily_avg(page),
        artists_count=_get_artists_count(page),
        albums_count=_get_albums_count(page),
        tracks_count=_get_tracks_count(page),
        artists=_get_artists(page),
        albums=_get_albums(page),
        tracks=_get_tracks(page),
        artists_top_new=_get_artists_top_new(page),
        albums_top_new=_get_albums_top_new(page),
        tracks_top_new=_get_tracks_top_new(page),
        listening_time_hours=_get_listening_time_hours(page),
    )


def _int(number: str) -> int:
    n = (
        number.replace(",", "")
        .replace("scrobbles", "")
        .strip()
        .lstrip("days,")
        .rstrip("hours")
        .strip()
    )
    assert n.isnumeric()
    return int(n)


def _get_scrobbles_count(page: BeautifulSoup) -> int:
    assert (_1 := page.select_one(".report-headline-total")) is not None
    return _int(_1.text)


def _get_scrobbles_daily_avg(page: BeautifulSoup) -> int:
    needle: str = "Average scrobbles"
    for fact in (facts := page.select(".report-box-container--quick-fact")):
        if needle not in fact.text:
            continue

        assert (_1 := fact.select_one(".quick-fact-data-value")) is not None
        return _int(_1.text)

    else:
        raise Exception(f"could not find '{needle}' fact, {len(facts)=}")


def _get_listening_time_hours(page: BeautifulSoup) -> int:
    needle: str = "Listening time"
    for fact in (facts := page.select(".report-box-container--quick-fact")):
        if needle not in fact.text:
            continue

        assert (_d1 := fact.select_one(".quick-fact-data-value")) is not None
        days: int = _int(_d1.text)

        assert (_h1 := fact.select_one(".quick-fact-data-detail")) is not None
        hours: int = _int(_h1.text)

        return (days * 24) + hours

    else:
        raise Exception(f"could not find '{needle}' fact, {len(facts)=}")


def _get_overview_scrobbles(page: BeautifulSoup, needle: str) -> int:
    assert (_1 := page.select_one(needle)) is not None
    assert (_2 := _1.select_one(".top-item-overview__scrobbles")) is not None
    return _int(_2.text)


def _get_artists_count(page: BeautifulSoup) -> int:
    return _get_overview_scrobbles(page=page, needle=".top-item-overview--artist")


def _get_albums_count(page: BeautifulSoup) -> int:
    return _get_overview_scrobbles(page=page, needle=".top-item-overview--album")


def _get_tracks_count(page: BeautifulSoup) -> int:
    return _get_overview_scrobbles(page=page, needle=".top-item-overview--track")


def _get_top_overview(
    page: BeautifulSoup,
    top_id: str,
    view_needle: str,
    select_needle: str,
) -> tuple[ThingWithScrobbles, ...]:
    things: list[ThingWithScrobbles] = []

    # top
    assert (_11 := page.select_one(top_id)) is not None
    assert (_12 := _11.select_one(".top-item-modal-header")) is not None
    assert (_13 := _11.select_one(".top-item-modal-data-item-value")) is not None
    assert (_14 := _11.select_one(".top-item-modal-link-text")) is not None
    assert view_needle in _14.text, "they moved the damn button"

    things.append(
        ThingWithScrobbles(
            name=_12.text.strip(),
            scrobbles=_int(_13.text),
            url=f"https://www.last.fm{_14.attrs.get('href', '/')}",
        )
    )

    # the rest
    for top in page.select(".listening-report-row__col--top-items"):
        if len(top.select(select_needle)) == 0:
            continue

        assert (_n := top.select(".listening-report-secondary-top-item-name")) is not None
        assert (
            _v := top.select(".listening-report-secondary-top-item-value")
        ) is not None
        assert len(_n) == len(_v)

        for n, v in zip(
            [x.text.strip() for x in _n],
            [_int(y.text) for y in _v],
        ):
            things.append(ThingWithScrobbles(name=n, scrobbles=v))

        return tuple(things)

    else:
        raise Exception(f"could not find '{select_needle}' top overview")


def _get_artists(page: BeautifulSoup) -> tuple[ThingWithScrobbles, ...]:
    return _get_top_overview(
        page=page,
        top_id="#top-artist",
        view_needle="View Artist page",
        select_needle=".top-item-overview--artist",
    )


def _get_albums(page: BeautifulSoup) -> tuple[ThingWithScrobbles, ...]:
    return _get_top_overview(
        page=page,
        top_id="#top-album",
        view_needle="View Album page",
        select_needle=".top-item-overview--album",
    )


def _get_tracks(page: BeautifulSoup) -> tuple[ThingWithScrobbles, ...]:
    return _get_top_overview(
        page=page,
        top_id="#top-track",
        view_needle="View Track page",
        select_needle=".top-item-overview--track",
    )


def _get_top_new_thing(page: BeautifulSoup, select_needle: str) -> ThingWithScrobbles:
    for top in page.select(".listening-report-row__col--top-items"):
        if len(top.select(select_needle)) == 0:
            continue

        assert (_t := top.select_one(".top-new-item-title")) is not None
        assert (_c := top.select_one(".top-new-item-count")) is not None

        name: str = _t.text.strip()
        scrobbles: str = _c.text.replace("scrobbles", "").replace(",", "").strip()

        return ThingWithScrobbles(
            name=name if scrobbles.isnumeric() else "",
            scrobbles=int(scrobbles) if scrobbles.isnumeric() else 0,
        )

    else:
        raise Exception(f"could not find '{select_needle}' top overview")


def _get_artists_top_new(page: BeautifulSoup) -> ThingWithScrobbles:
    return _get_top_new_thing(page=page, select_needle=".top-new-item-type__artist")


def _get_albums_top_new(page: BeautifulSoup) -> ThingWithScrobbles:
    return _get_top_new_thing(page=page, select_needle=".top-new-item-type__album")


def _get_tracks_top_new(page: BeautifulSoup) -> ThingWithScrobbles:
    return _get_top_new_thing(page=page, select_needle=".top-new-item-type__track")


def _rank(
    r: ListeningReport, rs: list[ListeningReport], k: Callable[[ListeningReport], int]
):
    ranking: list[ListeningReport] = []
    for _r in rs:
        insort(ranking, _r, key=k)

    for i, _r in enumerate(reversed(ranking), start=1):
        if _r == r:
            return i
    else:
        return 0


def make_circle_report(
    listening_reports: list[ListeningReport],
    behaviour: Behaviour,
) -> str:
    text: list[str] = []

    if behaviour.header != "":
        match behaviour.format:
            case FormatTypeEnum.ASCII:
                text.append(behaviour.header)
                text.append(("-" * len(behaviour.header)))
                text.append("")

            case FormatTypeEnum.TELEGRAM:
                text.append(behaviour.header + "\n")

    for leaderboard_pos, report in enumerate(
        reversed(
            sorted(
                listening_reports,
                key=lambda r: r.listening_time_hours + r.scrobbles_count,
            )
        ),
        start=1,
    ):
        text.append(
            report.to_str(
                behaviour=behaviour,
                leaderboard_pos=leaderboard_pos,
                leaderboard_scrobble_pos=_rank(
                    r=report,
                    rs=listening_reports,
                    k=lambda r: r.scrobbles_count,
                ),
                leaderboard_artists_pos=_rank(
                    r=report,
                    rs=listening_reports,
                    k=lambda r: r.artists_count,
                ),
                leaderboard_albums_pos=_rank(
                    r=report,
                    rs=listening_reports,
                    k=lambda r: r.albums_count,
                ),
                leaderboard_tracks_pos=_rank(
                    r=report,
                    rs=listening_reports,
                    k=lambda r: r.tracks_count,
                ),
                leaderboard_n=len(listening_reports),
            )
            + "\n"
        )

    return "\n".join(text)


def cli() -> None:
    behaviour = handle_args()
    limiter = Limiter()
    reports: list[ListeningReport] = []

    print(behaviour, file=stderr) if behaviour.verbose else ...
    for i, target in enumerate(set(behaviour.targets)):
        try:
            reports.append(
                get_listening_report(
                    target=target,
                    behaviour=behaviour,
                    limiter=limiter,
                )
            )

        except Exception as err:
            print(
                f"error: skipping target '{target}'\n"
                + indent(
                    "".join(format_exception(type(err), err, err.__traceback__)),
                    prefix="\t",
                )
            )

        else:
            print(
                f"got {target}'s reports... ({i + 1}/{len(behaviour.targets)})",
                file=stderr,
            )
            print(reports[-1], file=stderr) if behaviour.verbose else ...

    print(file=stderr)
    print(make_circle_report(listening_reports=reports, behaviour=behaviour))


if __name__ == "__main__":
    cli()
