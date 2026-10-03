
import os
import sys

_DATA_DIRNAME = "glimmerveil-anchor"

_WIN_DIRNAME = "Glimmerveil Anchor"
_MAC_DIRNAME = "Glimmerveil Anchor"

HOME_DIRNAME = "anchor"


def is_windows():
    return sys.platform.startswith("win")


def is_macos():
    return sys.platform == "darwin"


def base_dir():
    if is_windows():
        return (os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or os.path.expanduser(os.path.join("~", "AppData", "Local")))
    if is_macos():
        return os.path.expanduser(os.path.join("~", "Library", "Application Support"))
    return os.path.expanduser(os.path.join("~", ".local", "share"))


def _platform_dirname(linux_name):
    if is_windows():
        return _WIN_DIRNAME
    if is_macos():
        return _MAC_DIRNAME
    return linux_name


def forge_places():
    base = base_dir()
    return [os.path.join(base, "glimmerveil-forge"),
            os.path.join(base, "Glimmerveil Forge"),
            os.path.join(base, "glimmerveil"),
            os.path.join(base, "Glimmerveil"),
            os.path.expanduser(os.path.join("~", "veil"))]


def _norm(path):
    return os.path.normcase(os.path.realpath(os.path.expanduser(path)))


def is_forge_place(path):
    p = _norm(path)
    for f in forge_places():
        f = _norm(f)
        if p == f or p.startswith(f.rstrip(os.sep) + os.sep):
            return True
    return False


def refuse_forge(path, what):
    if path and is_forge_place(path):
        sys.exit("Anchor will not open %s at %s — that folder belongs to Glimmerveil Forge, and Anchor "
                 "never touches a Forge companion. Point it somewhere else (unset VEIL_PEEPS / VEIL_DATA "
                 "to use Anchor's own home, ~/%s)." % (what, path, HOME_DIRNAME))
    return path


PATH_ENVS = ("VEIL_DATA", "VEIL_PEEPS", "VEIL_DB", "VEIL_HISTORY", "VEIL_CARD_JSON", "VEIL_HEARTBEAT",
             "VEIL_PEPPER", "VEIL_VOICE_DIR", "VEIL_RAILS_DIR", "VEIL_SAFE_DIR")


def refuse_forge_env():
    for k in PATH_ENVS:
        refuse_forge(os.environ.get(k), "%s" % k)


DEFAULT_MODEL_NAME = "Qwen2.5-7B-Instruct-abliterated-v2.Q8_0.gguf"


def model_path():
    return os.environ.get("VEIL_MODEL") or os.path.expanduser(
        os.path.join("~", HOME_DIRNAME, "models", DEFAULT_MODEL_NAME))


def data_dir():
    env = os.environ.get("VEIL_DATA")
    d = env if env else os.path.join(base_dir(), _platform_dirname(_DATA_DIRNAME))
    return refuse_forge(d, "its app data")


def utf8_console():
    if not is_windows():
        return
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:replace")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def describe():
    return {
        "platform": sys.platform,
        "VEIL_DATA": os.environ.get("VEIL_DATA"),
        "XDG_DATA_HOME": os.environ.get("XDG_DATA_HOME"),
        "base_dir": base_dir(),
        "data_dir": data_dir(),
    }


if __name__ == "__main__":
    for k, v in describe().items():
        print("%-14s %s" % (k, v))
