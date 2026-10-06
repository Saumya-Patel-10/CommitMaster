"""
Generate the publication-quality PDF guide:
'CommitMaster_Store_Deployment_and_Admin_Guide.pdf'
Uses Microsoft Edge headless to render modern CSS/HTML to PDF.
"""
import os
import subprocess
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_PATH = os.path.join(APP_DIR, "guide_temp.html")
PDF_PATH = os.path.join(APP_DIR, "CommitMaster_Store_Deployment_and_Admin_Guide.pdf")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CommitMaster — Microsoft Store Deployment & Admin Guide</title>
<style>
  @page {
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
  }
  * {
    box-sizing: border-box;
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1f2328;
    background-color: #ffffff;
    line-height: 1.55;
    font-size: 13.5px;
    margin: 0;
    padding: 0;
  }

  /* Header Cover / Hero */
  .hero {
    background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
    color: #ffffff;
    padding: 24px;
    border-radius: 8px;
    margin-bottom: 24px;
    border-left: 6px solid #2ea043;
    display: flex;
    align-items: center;
    gap: 20px;
  }
  .hero-logo {
    width: 72px;
    height: 72px;
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(46, 160, 67, 0.35);
  }
  .hero-content {
    flex: 1;
  }
  .hero h1 {
    margin: 0 0 6px 0;
    font-size: 22px;
    letter-spacing: -0.5px;
    color: #ffffff;
  }
  .hero .subtitle {
    font-size: 13.5px;
    color: #8b949e;
    margin: 0 0 10px 0;
  }
  .hero .meta {
    font-size: 11.5px;
    color: #58a6ff;
    display: flex;
    gap: 16px;
  }

  h2 {
    color: #0d1117;
    border-bottom: 1.5px solid #d0d7de;
    padding-bottom: 6px;
    margin-top: 24px;
    margin-bottom: 12px;
    font-size: 17px;
    page-break-after: avoid;
  }
  h3 {
    color: #1f2328;
    margin-top: 16px;
    margin-bottom: 8px;
    font-size: 14.5px;
    page-break-after: avoid;
  }

  p {
    margin: 0 0 10px 0;
  }

  .badge {
    display: inline-block;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 12px;
    margin-right: 4px;
  }
  .badge-user {
    background-color: #dafbe1;
    color: #1a7f37;
    border: 1px solid #4ac26b;
  }
  .badge-admin {
    background-color: #ddf4ff;
    color: #0969da;
    border: 1px solid #54aeff;
  }
  .badge-warn {
    background-color: #fff8c5;
    color: #9a6700;
    border: 1px solid #d4a72c;
  }

  /* Callout boxes */
  .callout {
    padding: 12px 16px;
    border-radius: 6px;
    margin: 12px 0;
    font-size: 12.5px;
  }
  .callout-info {
    background-color: #f6f8fa;
    border-left: 4px solid #0969da;
    color: #24292f;
  }
  .callout-success {
    background-color: #f0fff4;
    border-left: 4px solid #2da44e;
    color: #1a7f37;
  }
  .callout-danger {
    background-color: #fff8f8;
    border-left: 4px solid #cf222e;
    color: #82071e;
  }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0 16px 0;
    font-size: 12px;
    page-break-inside: avoid;
  }
  th {
    background-color: #f6f8fa;
    color: #24292f;
    font-weight: 600;
    text-align: left;
    padding: 7px 10px;
    border: 1px solid #d0d7de;
  }
  td {
    padding: 7px 10px;
    border: 1px solid #d0d7de;
    vertical-align: top;
  }
  tr:nth-child(even) td {
    background-color: #fcfcfc;
  }

  /* Code & Shortcuts */
  code {
    background-color: #eff1f3;
    padding: 2px 5px;
    border-radius: 4px;
    font-family: Consolas, "Liberation Mono", Menlo, Courier, monospace;
    font-size: 12px;
    color: #b31d28;
  }
  pre {
    background-color: #f6f8fa;
    padding: 10px 12px;
    border-radius: 6px;
    border: 1px solid #d0d7de;
    font-family: Consolas, monospace;
    font-size: 11.5px;
    overflow-x: auto;
    margin: 8px 0;
  }
  kbd {
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-bottom: 2px solid #afb8c1;
    border-radius: 3px;
    box-shadow: inset 0 -1px 0 #afb8c1;
    color: #24292f;
    display: inline-block;
    font-size: 11px;
    line-height: 10px;
    padding: 3px 5px;
  }

  /* Cards for Clickable launchers */
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin: 12px 0;
  }
  .card {
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 12px 14px;
    background: #fbfcfd;
  }
  .card h4 {
    margin: 0 0 4px 0;
    font-size: 13px;
    color: #0969da;
  }
  .card p {
    font-size: 11.5px;
    color: #57606a;
    margin: 0;
  }

  .page-break {
    page-break-before: always;
  }
</style>
</head>
<body>

  <div class="hero">
    <img class="hero-logo" src="data:image/png;base64,__LOGO_B64__" alt="CommitMaster Logo">
    <div class="hero-content">
      <h1>CommitMaster — Microsoft Store Deployment & Admin Guide</h1>
      <div class="subtitle">Complete Packaging Manual, Microsoft Store Distribution Guide, and Private Admin App Documentation</div>
      <div class="meta">
        <span><b>Project:</b> CommitMaster Desktop</span>
        <span><b>Version:</b> 2.0.0</span>
        <span><b>Author:</b> Saumya Patel</span>
        <span><b>OS Target:</b> Windows 10 / 11 (x64)</span>
      </div>
    </div>
  </div>

  <h2>1. Overview: The Two Separate Applications</h2>
  <p>
    CommitMaster is divided into two distinct applications designed for completely different audiences. Understanding this boundary ensures your personal admin privileges remain secure:
  </p>
  <table>
    <thead>
      <tr>
        <th style="width: 22%;">Application</th>
        <th style="width: 22%;">Target Audience</th>
        <th style="width: 26%;">Entry Point / Binary</th>
        <th style="width: 30%;">Purpose & Access Level</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><b>Public User App</b><br><span class="badge badge-user">Public Release</span></td>
        <td>End users, developers, team members, public downloaders.</td>
        <td><code>app.py</code><br>Compiled to: <code>CommitMaster.exe</code></td>
        <td>Standard developer tool: AI commit messages, Git Desktop diff viewer, security inspection, local watched repositories. <i>Zero administrative controls.</i></td>
      </tr>
      <tr>
        <td><b>Private Admin App</b><br><span class="badge badge-admin">Saumya Only</span></td>
        <td><b>Saumya only</b> (personal operator instance).</td>
        <td><code>admin_app.py</code><br>Compiled to: <code>CommitMaster-Admin.exe</code></td>
        <td>Full unified operator portal: manage all user accounts, view system activity logs, analyze multi-user commit charts, configure system settings, and inspect database state.</td>
      </tr>
    </tbody>
  </table>

  <div class="callout callout-danger">
    <b>CRITICAL SECURITY RULE:</b> NEVER upload <code>CommitMaster-Admin.exe</code> to the Microsoft Store or public GitHub releases. Only upload <code>CommitMaster.exe</code> for public distribution. Keep the Admin App exclusively on your private PC.
  </div>

  <h2>2. Clickable Single-Click Launchers (No Terminal Needed!)</h2>
  <p>
    You do not need to open a terminal or type Python commands to run or build the apps. Three pre-configured single-click desktop helpers are provided in your project root:
  </p>

  <div class="grid">
    <div class="card">
      <h4>🖱️ Launch_Admin_App.vbs</h4>
      <p><b>Double-click to start your Admin App instantly.</b> Runs completely silently in the background with <i>zero black terminal or command prompt windows flashing</i>.</p>
    </div>
    <div class="card">
      <h4>🖱️ Launch_Admin_App.bat</h4>
      <p><b>Standard batch launcher fallback.</b> Launches <code>admin_app.py</code> using <code>pythonw.exe</code>.</p>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h4>⚙️ Build_All_Packages.bat</h4>
      <p><b>One-click automated compiler.</b> Compiles both <code>CommitMaster.exe</code> (User App) and <code>CommitMaster-Admin.exe</code> (Admin App) and generates a release ZIP archive in the <code>dist/</code> folder.</p>
    </div>
    <div class="card">
      <h4>📌 Desktop Shortcut Creation</h4>
      <p>Right-click <code>Launch_Admin_App.vbs</code> &rarr; <b>Show more options</b> &rarr; <b>Send to</b> &rarr; <b>Desktop (create shortcut)</b> to have a permanent 1-click icon on your desktop.</p>
    </div>
  </div>

  <h2>3. What Files Are Compressed Into the Downloadable .EXE</h2>
  <p>
    When you double-click <code>Build_All_Packages.bat</code>, PyInstaller compresses the Python runtime, graphical engines, and all project modules into self-contained single-file binaries.
  </p>
  <table>
    <thead>
      <tr>
        <th>Category</th>
        <th>What Is Packaged Inside the EXE</th>
        <th>Why It Is Included</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><b>Python Runtime</b></td>
        <td><code>python3xx.dll</code>, C-runtime libraries, standard library modules</td>
        <td>Allows anyone to run CommitMaster without needing Python installed on their computer.</td>
      </tr>
      <tr>
        <td><b>GUI Engine</b></td>
        <td>Tcl/Tk binaries (<code>tcl86t.dll</code>, <code>tk86t.dll</code>) and Tkinter asset library</td>
        <td>Powers the custom modern dark-mode desktop window, charts, and smooth scrolling.</td>
      </tr>
      <tr>
        <td><b>Application Modules</b></td>
        <td>
          The entire <code>commitmaster/</code> module package:<br>
          • <code>user_dashboard.py</code> & <code>admin_portal.py</code><br>
          • <code>navigation.py</code> (Smooth scroll & middle-click autoscroll)<br>
          • <code>commit_engine.py</code> (Git porcelain & repo integration)<br>
          • <code>file_inspector.py</code> (Pre-commit security & syntax scanner)<br>
          • <code>charts.py</code> (Interactive multi-series analytics)<br>
          • <code>ai_messages.py</code> (AI commit message generation)<br>
          • <code>database.py</code> (SQLite models & queries)
        </td>
        <td>All business logic, security scanners, user interfaces, and engines are bundled directly inside the executable.</td>
      </tr>
      <tr>
        <td><b>Third-Party Packages</b></td>
        <td><code>Pillow</code> (PIL), <code>pystray</code>, <code>psutil</code>, <code>requests</code>, <code>urllib3</code></td>
        <td>Background process monitoring, tray icon integration, and network requests.</td>
      </tr>
      <tr>
        <td><b>Application Icon</b></td>
        <td><code>icon.ico</code></td>
        <td>Windows shell icon, Alt+Tab switcher icon, and taskbar branding.</td>
      </tr>
    </tbody>
  </table>

  <div class="callout callout-info">
    <b>Runtime Data Files (Stored in AppData):</b><br>
    The local SQLite database (<code>commitmaster.db</code>), settings (<code>config.json</code>), auto-login tokens (<code>.session_token</code>), and log files (<code>commitmaster.log</code>) are <b>not</b> embedded inside the exe. They are automatically created in <code>%LOCALAPPDATA%\\CommitMaster</code> on the user's PC, ensuring data persists across updates.
  </div>

  <div class="page-break"></div>

  <h2>4. Publishing to the Microsoft Store</h2>
  <p>
    Microsoft provides two official methods to publish Win32 desktop apps to the Microsoft Store:
  </p>

  <h3>Method A: Direct Win32 (.EXE) Submission via URL (Recommended & Easiest)</h3>
  <p>
    Since 2021, Microsoft allows developers to submit standard Windows desktop applications directly:
  </p>
  <ol>
    <li>Compile the user binary by double-clicking <code>Build_All_Packages.bat</code>.</li>
    <li>Go to your GitHub repository and create a new Release (e.g., <code>v2.0.0</code>).</li>
    <li>Attach <code>dist/CommitMaster.exe</code> to the GitHub Release.</li>
    <li>In <b>Microsoft Partner Center</b>, create a new submission and choose <b>Win32 App</b>.</li>
    <li>Enter the download URL of your GitHub release:
      <pre>https://github.com/Saumya-Patel-10/CommitMaster/releases/download/v2.0.0/CommitMaster.exe</pre>
    </li>
    <li>Provide silent installer arguments: <code>/SILENT</code> or leave blank for portable exes.</li>
    <li>Submit for certification. Microsoft's automated bots download, scan, and list the app.</li>
  </ol>

  <h3>Method B: MSIX Package via MSIX Packaging Tool (Best for Clean Sandbox)</h3>
  <p>
    MSIX packages install cleanly like native Windows Store apps and update automatically through the Store:
  </p>
  <ol>
    <li>Install the official free <b>MSIX Packaging Tool</b> from the Microsoft Store.</li>
    <li>Open the tool and choose <b>Application package on this computer</b>.</li>
    <li>Select <code>dist/CommitMaster.exe</code> as the application executable.</li>
    <li>Fill in your Package details:
      <ul>
        <li><b>Package Name:</b> <code>CommitMaster</code></li>
        <li><b>Publisher:</b> <code>CN=Your-Partner-Center-Publisher-ID</code></li>
        <li><b>Version:</b> <code>2.0.0.0</code></li>
      </ul>
    </li>
    <li>Click <b>Create Package</b> &rarr; Generates <code>CommitMaster.msix</code>.</li>
    <li>Upload <code>CommitMaster.msix</code> directly into Microsoft Partner Center.</li>
  </ol>

  <h2>5. Testing on the Microsoft Store Before Public Launch</h2>
  <p>
    You do not have to release your app to the public immediately. Microsoft Store provides two testing mechanisms:
  </p>

  <h3>1. Private Audience (Direct Link Only)</h3>
  <ul>
    <li>In Partner Center under <b>Pricing and availability</b> &rarr; <b>Visibility</b>:</li>
    <li>Select <b>Hidden in the Store. Only customers with a direct link can download</b>.</li>
    <li>The app is completely invisible in Microsoft Store search results. Only you and users you send the secret link to can install it.</li>
  </ul>

  <h3>2. Package Flighting (Closed Beta Channel)</h3>
  <ul>
    <li>Go to <b>Package flights</b> in the left navigation of your app submission.</li>
    <li>Create a flight group named <code>Beta-Testers</code>.</li>
    <li>Add your Microsoft account email address (and any friends/testers).</li>
    <li>Upload your test build to this flight. Only members of the group will receive the update through the Windows Store app!</li>
    <li>When testing is complete, click <b>Promote flight to submission</b> to roll it out to all users worldwide.</li>
  </ul>

  <h2>6. Admin App Operator Manual (Your Personal Tool)</h2>
  <p>
    Double-clicking <code>Launch_Admin_App.vbs</code> opens your unified personal administration dashboard. Key features include:
  </p>
  <table>
    <thead>
      <tr>
        <th style="width: 25%;">Section</th>
        <th style="width: 75%;">Capabilities & Controls</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><b>User Management</b></td>
        <td>
          • View all registered user accounts with avatar badges, email addresses, and roles.<br>
          • Promote users to <code>admin</code> or demote to <code>user</code>.<br>
          • Activate or deactivate user accounts instantly.<br>
          • Manually trigger administrative password resets.
        </td>
      </tr>
      <tr>
        <td><b>Activity Logs & Security</b></td>
        <td>
          • Complete audit log of all logins, repo scans, pre-commit inspections, and git pushes.<br>
          • Search and filter logs by username, action type, or date.<br>
          • Audit security issues caught before commits (secret leaks, merge conflict markers).
        </td>
      </tr>
      <tr>
        <td><b>Analytics & Charts</b></td>
        <td>
          • Interactive multi-series commit and scan charts with hover tooltips and clickable legends.<br>
          • Filter activity by 7 days, 30 days, or custom ranges.<br>
          • Identify peak committing hours and repository activity.
        </td>
      </tr>
      <tr>
        <td><b>Global Settings</b></td>
        <td>
          • Configure default sensitive file patterns (e.g. <code>.env</code>, <code>id_rsa</code>, <code>*.pem</code>).<br>
          • Set local AI model detection endpoints and fallbacks.<br>
          • Set background idle thresholds and monitoring intervals.
        </td>
      </tr>
    </tbody>
  </table>

  <h2>7. Professional Windows 11 Customization & Visual Assets</h2>
  <p>
    CommitMaster has been customized with full Windows 11 native desktop integration:
  </p>
  <ul>
    <li><b>Windows 11 Fluent App Icon:</b> A high-contrast dark squircle featuring glowing emerald green and cyan Git branch trees, commit nodes, and branding. Compiled directly into <code>icon.ico</code> with 16, 24, 32, 48, 64, 128, and 256 mipmap sizes.</li>
    <li><b>Windows Taskbar Identity (AppUserModelID):</b> Registered with <code>CommitMaster.Desktop.2.0</code> via Windows shell API, ensuring the taskbar groups CommitMaster under its own branded identity rather than a generic Python launcher.</li>
    <li><b>Immersive Dark Titlebar (DWM API):</b> Native Windows 10/11 titlebars are styled pitch dark (<code>DWMWA_USE_IMMERSIVE_DARK_MODE</code>), matching the application palette and eliminating bright white window borders.</li>
    <li><b>Microsoft Store Ready Assets:</b> Pre-generated icons in the <code>assets/</code> folder ready for Partner Center:
      <code>Square44x44Logo.png</code>, <code>Square150x150Logo.png</code>, and <code>StoreLogo.png</code> (300x300).
    </li>
  </ul>

  <div class="callout callout-success">
    <b>Summary Checklist:</b><br>
    ✔ <b>Run Admin App:</b> Double-click <code>Launch_Admin_App.vbs</code> on your PC (silent background launch).<br>
    ✔ <b>Build Executables:</b> Double-click <code>Build_All_Packages.bat</code> (compiles both User & Admin binaries).<br>
    ✔ <b>Deploy to Store:</b> Submit <code>dist/CommitMaster.exe</code> (or <code>.msix</code>) to Microsoft Partner Center.
  </div>

</body>
</html>
"""

def generate():
    import base64
    logo_path = os.path.join(APP_DIR, "assets", "logo_128.png")
    logo_b64 = ""
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")

    html_content = HTML_TEMPLATE.replace("__LOGO_B64__", logo_b64)

    print("Writing HTML guide source...")
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge_bin = None
    for p in edge_paths:
        if os.path.exists(p):
            edge_bin = p
            break

    if not edge_bin:
        print("[ERROR] Microsoft Edge binary not found.")
        sys.exit(1)

    print(f"Generating PDF using Edge at {edge_bin}...")
    cmd = [
        edge_bin,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        HTML_PATH,
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and os.path.exists(PDF_PATH):
        size_kb = os.path.getsize(PDF_PATH) / 1024
        print(f"\n[SUCCESS] PDF generated successfully!")
        print(f"   Location: {PDF_PATH}")
        print(f"   Size: {size_kb:.1f} KB")
        if os.path.exists(HTML_PATH):
            os.remove(HTML_PATH)
    else:
        print(f"[ERROR] PDF generation failed: {res.stderr}")
        sys.exit(1)

if __name__ == "__main__":
    generate()
