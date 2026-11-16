# Three CommitMaster applications

CommitMaster is three processes that can run at the same time. They are not three modes of one executable.

| | User | Admin | Demo |
|---|---|---|---|
| Entry | `app.py` | `admin_app.py` | `demo_app.py` |
| Process lock | `product.activate("user")` | `edition.set_admin_edition()` | `product.activate("demo")` before it calls the user session |
| Executable | `CommitMaster-User.exe` | `CommitMaster-Admin.exe` | `CommitMaster-Demo.exe` |
| Data directory | `%LOCALAPPDATA%\CommitMaster` | `%LOCALAPPDATA%\CommitMaster-Admin` | `%LOCALAPPDATA%\CommitMaster-Demo` |
| Database | `commitmaster.db` in that directory | its own `commitmaster.db` | its own `commitmaster.db` |
| Config | `config.json` in that directory | its own `config.json` | its own `config.json` |
| AppUserModelID | `CommitMaster.App.User` | `CommitMaster.App.Admin` | `CommitMaster.App.Demo` |
| Start Menu name | CommitMaster User | CommitMaster Admin | CommitMaster Demo |
| Icon | `icon_user.ico` | `icon_admin.ico` | `icon_demo.ico` |

The user package name stays `SaumyaPatel.CommitMaster`. The publisher stays `CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8`. Version `1.1.0.0` in `store_identity.json` is unchanged. This document does not publish that package.

## What the user process cannot do

`app.py` does not import `admin_app`. After the user or demo process locks its product, a later call cannot switch it to admin. `--admin` and `--admin-edition` are ignored. The user dashboard has no path that opens the admin window.

The admin app is a separate process. When it opens someone's workspace, it starts `CommitMaster-User.exe` (or `python app.py`) with a handoff file. That file cannot carry an admin scope, a password, or a token other than the user session it was issued.

## Data directories

`commitmaster.paths.get_data_dir` follows the locked product. A source checkout that still has `commitmaster.db` in the repository is not the runtime directory for any edition.

The user product may copy `commitmaster.db`, `config.json`, `.commitmaster_accounts.json`, and `commitmaster.log` once, and only when its own folder has no database yet. It does not copy `.session_token`, `.admin_session`, `.admin_initial_secret`, or `server_commitmaster.db`. Admin and demo start with empty folders. A frozen build does not copy the workspace database.

`COMMITMASTER_DATA_DIR` is a root. User, admin, and demo each receive a child folder with the names above. If the variable already ends in this product's folder, that path is used. If it ends in another product's folder, `DataDirectoryError` is raised and no database is created there.

## Shell identity

`commitmaster.windows_integration` keeps one shortcut title, executable name, and icon per edition. `create_desktop_shortcut` uses the target it is given: `user`, `admin`, `demo`, or `both` (user and admin). It does not rewrite that target to the user app.

A running process registers only its own Start Menu shortcut. The demo process writes `CommitMaster Demo.lnk` and does not write `CommitMaster User.lnk`. The taskbar id is set once from the locked product, so a later window cannot move the demo process into the user taskbar group.

`Launch_CommitMaster.vbs` creates `CommitMaster User.lnk`. `Launch_Admin_App.vbs` creates `CommitMaster Admin.lnk`. `Launch_Demo_App.vbs` creates `CommitMaster Demo.lnk`.

These shortcuts are how a source or exe launch registers itself on Windows. They are not MSIX packages. Signing, Store submission, and version tags are outside this change. A Windows 11 Start Menu install was not exercised by the automated tests, which run without creating shortcuts.
