from pathlib import Path
from streamlit.web.bootstrap import run


def main() -> None:
    app_path = Path(__file__).parent / "app.py"
    run(str(app_path), is_hello=False, args=[], flag_options=[])


if __name__ == "__main__":
    main()
