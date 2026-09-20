from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class MovieCandidate:
    imdb_id: str
    title: str
    rating: float | None = None
    year: int | None = None


@dataclass(frozen=True, slots=True)
class Movie:
    imdb_id: str
    title: str
    original_title: str
    overview: str
    poster_url: str | None
    rating: float | None
    year: int | None
    genres: tuple[str, ...]

    def localized(self, *, title: str | None = None, overview: str | None = None) -> "Movie":
        return replace(
            self,
            title=(title or self.title).strip(),
            overview=(overview or self.overview).strip(),
        )


@dataclass(frozen=True, slots=True)
class StoredMovie:
    imdb_id: str
    title: str
    year: int | None
    poster_url: str | None
    watched: bool
    skipped: bool
    favorite: bool
    watchlist: bool
