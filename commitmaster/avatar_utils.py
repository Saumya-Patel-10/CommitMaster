"""
CommitMaster — Avatar & Profile Picture Utilities.
===================================================
Provides custom avatar generation, image uploading, rounded cropping,
and caching for account profile pictures across the application.
"""
import os
import sys
import shutil
from typing import Any, Dict, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageTk

from commitmaster import paths

APP_DIR = paths.get_data_dir()
AVATARS_DIR = paths.get_avatars_dir()

_PHOTO_CACHE: Dict[str, ImageTk.PhotoImage] = {}


def ensure_avatars_dir() -> str:
    """Ensure the assets/avatars directory exists."""
    os.makedirs(AVATARS_DIR, exist_ok=True)
    return AVATARS_DIR


def save_avatar_image(user_id: int, source_path: str) -> Tuple[bool, str]:
    """
    Load an image from source_path, center-crop to a square, resize to 256x256,
    and save into the local avatars directory for user_id.
    Updates the database and account_manager.
    Returns (success, new_file_path_or_error).
    """
    try:
        ensure_avatars_dir()
        if not os.path.exists(source_path):
            return False, "Selected image file does not exist."

        dest_path = os.path.join(AVATARS_DIR, f"user_{user_id}.png")

        with Image.open(source_path) as img:
            img = img.convert("RGBA")
            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            cropped = img.crop((left, top, left + min_dim, top + min_dim))
            resized = cropped.resize((256, 256), Image.Resampling.LANCZOS)
            resized.save(dest_path, format="PNG")

        # Update database
        from commitmaster import database as db
        conn = db.get_conn()
        conn.execute("UPDATE users SET avatar_image = ? WHERE id = ?", (dest_path, user_id))
        conn.commit()

        # Update local account manager
        try:
            from commitmaster import account_manager
            accounts = account_manager.get_saved_accounts()
            for acc in accounts:
                if acc.get("id") == user_id:
                    acc["avatar_image"] = dest_path
                    account_manager.save_account(acc)
                    break
        except Exception:
            pass

        # Invalidate memory cache
        _invalidate_cache(user_id)
        return True, dest_path
    except Exception as exc:
        return False, f"Failed to save profile picture: {exc}"


def remove_avatar_image(user_id: int) -> bool:
    """Remove user's custom avatar image and revert to generated logo."""
    try:
        dest_path = os.path.join(AVATARS_DIR, f"user_{user_id}.png")
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass

        from commitmaster import database as db
        conn = db.get_conn()
        conn.execute("UPDATE users SET avatar_image = '' WHERE id = ?", (user_id,))
        conn.commit()

        try:
            from commitmaster import account_manager
            accounts = account_manager.get_saved_accounts()
            for acc in accounts:
                if acc.get("id") == user_id:
                    acc["avatar_image"] = ""
                    account_manager.save_account(acc)
                    break
        except Exception:
            pass

        _invalidate_cache(user_id)
        return True
    except Exception:
        return False


def _invalidate_cache(user_id: int) -> None:
    prefix = f"user_{user_id}_"
    keys_to_remove = [k for k in _PHOTO_CACHE if k.startswith(prefix)]
    for k in keys_to_remove:
        _PHOTO_CACHE.pop(k, None)


def get_avatar_photo(
    user: Dict[str, Any],
    size: int = 40,
    rounded: bool = True,
    master: Any = None
) -> Optional[ImageTk.PhotoImage]:
    """
    Return a high-resolution PhotoImage for the user's avatar.
    If the user has a custom uploaded avatar_image, it is rendered with rounded edges.
    Otherwise, an attractive circular badge with the user's background color and initials is rendered.
    """
    user_id = user.get("id", 0)
    img_path = user.get("avatar_image", "")
    color = user.get("avatar_color", "#3fb950")
    initials = _get_initials(user)

    cache_key = f"user_{user_id}_{size}_{rounded}_{img_path}_{color}_{initials}"
    if cache_key in _PHOTO_CACHE:
        try:
            photo = _PHOTO_CACHE[cache_key]
            if master:
                master.tk.call("image", "type", str(photo))
            return photo
        except Exception:
            _PHOTO_CACHE.pop(cache_key, None)

    try:
        if img_path and os.path.exists(img_path):
            with Image.open(img_path) as raw:
                raw = raw.convert("RGBA")
                raw = raw.resize((size, size), Image.Resampling.LANCZOS)
                if rounded:
                    mask = Image.new("L", (size * 2, size * 2), 0)
                    draw = ImageDraw.Draw(mask)
                    draw.ellipse((0, 0, size * 2 - 1, size * 2 - 1), fill=255)
                    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
                    final_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                    final_img.paste(raw, (0, 0), mask=mask)
                else:
                    final_img = raw
        else:
            # Generate custom monogram logo badge
            scale = 2
            s = size * scale
            badge = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(badge)
            if rounded:
                draw.ellipse((0, 0, s - 1, s - 1), fill=color)
            else:
                draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.15), fill=color)

            # Try to load a clean font or use default
            font_size = max(10, int(s * 0.42))
            font = None
            for font_name in ("segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf"):
                try:
                    font = ImageFont.truetype(font_name, font_size)
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()

            # Center text in badge
            bbox = draw.textbbox((0, 0), initials, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (s - tw) / 2 - bbox[0]
            ty = (s - th) / 2 - bbox[1]
            draw.text((tx, ty), initials, fill="white", font=font)

            final_img = badge.resize((size, size), Image.Resampling.LANCZOS)

        photo = ImageTk.PhotoImage(final_img, master=master)
        _PHOTO_CACHE[cache_key] = photo
        return photo
    except Exception:
        return None


def _get_initials(user: Dict[str, Any]) -> str:
    name = (user.get("full_name") or user.get("username") or "CM").strip()
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper()
