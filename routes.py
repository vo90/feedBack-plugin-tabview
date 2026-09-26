"""Tab View plugin — serves Guitar Pro files converted from arrangements."""

import sys
import tempfile
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import Response, JSONResponse

# Ensure the song lib is importable
_lib = str(Path(__file__).resolve().parent.parent.parent / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

# `sloppak` is loaded lazily inside the song-package branch below — older
# cores ship without lib/sloppak.py, and a top-level import here would
# disable Tab View entirely on those installs.

# Song-package suffixes: `.feedpak` is the current extension, `.sloppak` the
# legacy one — same on-disk format either way (mirrors core lib/sloppak.py
# SONG_EXTS, which can't be imported here without breaking the lazy import).
PAK_EXTS = (".feedpak", ".sloppak")


def setup(app: FastAPI, context: dict):
    get_dlc_dir = context["get_dlc_dir"]
    get_sloppak_cache = context.get("get_sloppak_cache_dir")

    from rs2gp import arrangement_to_gp5
    from rhythm import RhythmError

    def _song_to_gp5(song, arrangement: int, harmonics: bool = False, continuations=None, strum_context=None) -> Response:
        if not song.arrangements:
            return Response("No arrangements found", status_code=404)
        idx = max(0, min(arrangement, len(song.arrangements) - 1))
        gp5_bytes = arrangement_to_gp5(song, idx, include_harmonics=harmonics, strum_context=strum_context)
        if harmonics:
            gp5_bytes['sourceHarmonicContinuations']=continuations or []
            return JSONResponse(gp5_bytes)
        return Response(
            content=gp5_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": 'attachment; filename="tab.gp5"'},
        )

    @app.get("/api/plugins/tabview/gp5/{filename:path}")
    def tabview_gp5(filename: str, arrangement: int = 0, harmonics: bool = False):
        dlc = get_dlc_dir()
        if not dlc:
            return Response("DLC folder not configured", status_code=500)

        song_path = Path(dlc) / filename

        # Path traversal guard: reject any filename that resolves outside dlc.
        dlc_resolved = Path(dlc).resolve()
        try:
            resolved = song_path.resolve()
        except Exception:
            return Response("Path resolution failed", status_code=400)
        if resolved != dlc_resolved and dlc_resolved not in resolved.parents:
            return Response("Path traversal not allowed", status_code=400)

        if not song_path.exists():
            return Response("File not found", status_code=404)

        try:
            # Song package (zip-form *.feedpak / *.sloppak or directory-form
            # ending in either suffix): use the sloppak loader directly — it
            # accepts both extensions. Only directories whose name ends with
            # a package suffix are treated as packages; any other input is
            # rejected with a clear error below.
            is_pak = filename.lower().endswith(PAK_EXTS) or (
                song_path.is_dir() and song_path.name.lower().endswith(PAK_EXTS)
            )
            if is_pak:
                try:
                    import sloppak as sloppak_mod
                except ImportError:
                    return Response(
                        "Sloppak support requires a newer feedBack core (lib/sloppak.py). "
                        "Update the host.",
                        status_code=501,
                    )
                raw_cache = get_sloppak_cache() if get_sloppak_cache else None
                cache = Path(raw_cache) if raw_cache is not None else Path(tempfile.gettempdir()) / "sloppak_cache"
                cache.mkdir(parents=True, exist_ok=True)
                loaded = sloppak_mod.load_song(filename, Path(dlc), cache)
                continuations=[]
                relative=loaded.manifest.get('song_import',{}).get('tiedHarmonicsFile')
                if harmonics and isinstance(relative,str) and loaded.song.arrangements:
                    evidence=(loaded.source_dir/relative).resolve()
                    if not evidence.is_relative_to(loaded.source_dir.resolve()):
                        raise ValueError('Harmonic evidence path is outside the song')
                    if evidence.stat().st_size>8*1024*1024:raise ValueError('Harmonic evidence is too large')
                    retained=json.loads(evidence.read_text(encoding='utf-8'))
                    idx=max(0,min(arrangement,len(loaded.song.arrangements)-1))
                    track=loaded.arrangement_ids[idx]
                    continuations=[row for row in retained.get('continuations',[]) if row.get('trackId')==track]
                from strums import load_context
                idx=max(0,min(arrangement,len(loaded.song.arrangements)-1))
                context=load_context(loaded,idx) if loaded.song.arrangements else None
                return _song_to_gp5(loaded.song, arrangement, harmonics, continuations, context)

            # Any non-package input is unsupported.
            return Response(
                "Only .feedpak / .sloppak songs are supported",
                status_code=400,
            )
        except RhythmError as e:
            return Response(str(e), status_code=422)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(f"Conversion error: {e}", status_code=500)
