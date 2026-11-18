"""
CommitMaster — 3D Animated Hub Desktop Launcher.
Launches the full hardware-accelerated 3D Interactive Hub matching the futuristic specialist interface.
Usage: python launch_3d_hub.py
"""
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import webview_host


def main():
    print("=" * 60)
    print("Launching CommitMaster 3D Interactive Hub...")
    print("=" * 60)

    html_path = webview_host.get_web_dist_path()
    file_url = f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}#hub"

    if webview_host.is_webview2_available():
        try:
            import webview
            window = webview.create_window(
                title="CommitMaster — 3D Specialist Hub",
                url=file_url,
                width=1340,
                height=840,
                background_color="#050811",
                text_select=False,
            )
            webview.start()
            return
        except Exception as exc:
            print(f"Desktop webview launch note: {exc}")

    import webbrowser
    webbrowser.open(file_url)


if __name__ == "__main__":
    main()
