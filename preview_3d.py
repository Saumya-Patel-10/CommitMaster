"""
CommitMaster — 3D Interactive Features Preview Launcher.
Usage: python preview_3d.py [scene_name]
Example: python preview_3d.py commit_galaxy
Available scenes:
  commit_galaxy, architecture, security_map, analytics, agent_workflow,
  device_topology, diff_comparator, merge_simulator, health_globe,
  commit_timeline, workspace_switcher, deployment_pipeline
"""
import os
import sys
import webbrowser

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import scene_data, accessibility, webview_host


def main():
    scene = sys.argv[1] if len(sys.argv) > 1 else "commit_galaxy"
    print("=" * 60)
    print("CommitMaster 3D Interactive Viewport Preview")
    print("=" * 60)
    print(f"Target Scene: {scene}")

    # Check accessibility & performance classification
    state = accessibility.get_accessibility_state()
    print(f"Detected Performance Tier : {state['performance_tier']}")
    print(f"Reduced Motion Preference : {state['reduced_motion']}")
    print(f"GPU Classification        : {state['gpu'].get('name', 'Unknown')} ({state['gpu'].get('type', 'unknown')})")

    # Extract sample repo data for commit galaxy
    if scene == "commit_galaxy":
        data = scene_data.build_commit_galaxy_data(APP_DIR, max_commits=50)
        print(f"Loaded {data['summary'].get('totalCommits', 0)} commits across {data['summary'].get('totalBranches', 0)} branches.")
    elif scene == "architecture":
        data = scene_data.build_architecture_data(APP_DIR)
        print(f"Scanned {data['metrics'].get('totalFiles', 0)} files across {data['metrics'].get('totalDirectories', 0)} directories.")
    elif scene == "security_map":
        data = scene_data.build_security_data(APP_DIR)
        print(f"Scan complete. Health score: {data.get('healthScore', 100)}/100.")

    html_path = webview_host.get_web_dist_path()
    file_url = f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}#{scene}"

    # If pywebview is installed, open inside an app window; otherwise launch in system browser
    if webview_host.is_webview2_available():
        try:
            import webview
            print(f"\nLaunching in native WebView2 desktop container...")
            webview.create_window(
                f"CommitMaster 3D — {scene.replace('_', ' ').title()}",
                url=file_url,
                width=1280,
                height=800,
                background_color="#0a0e17",
            )
            webview.start()
            return
        except Exception as exc:
            print(f"pywebview desktop launch notice ({exc}); opening in default browser...")

    print(f"\nOpening 3D viewport in default browser:\n{file_url}")
    webbrowser.open(file_url)


if __name__ == "__main__":
    main()
