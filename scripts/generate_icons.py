"""Optional asset generation; delivered PNGs require no runtime graphics dependency."""
from pathlib import Path
import cairosvg
root = Path(__file__).resolve().parents[1] / 'miniapp/src/static'
(root / 'icons').mkdir(exist_ok=True)
paths = {
'user': '<circle cx="24" cy="15" r="7"/><path d="M9 43v-5a15 15 0 0 1 30 0v5Z"/>',
'camera': '<path d="M7 14h9l4-6h8l4 6h9v26H7Z"/><circle cx="24" cy="27" r="8"/>',
'image': '<rect x="5" y="7" width="38" height="34" rx="5"/><circle cx="32" cy="17" r="3"/><path d="m5 33 11-12 12 13 6-6 9 9"/>',
'document': '<path d="M11 4h18l10 10v30H11Z M29 4v11h10 M18 23h14 M18 30h14 M18 37h8"/>',
'book': '<path d="M24 42V10C16 3 7 5 3 8v31c8-4 16-2 21 3Zm0 0V10c8-7 17-5 21-2v31c-8-4-16-2-21 3Z"/>',
'leaf': '<path d="M24 43C7 36 6 23 9 15c12 0 18 12 15 28Zm0 0C14 19 28 8 39 3c6 17-1 32-15 40Z"/><path d="m24 40 10-23"/>',
'graph': '<circle cx="24" cy="8" r="5"/><circle cx="8" cy="38" r="5"/><circle cx="40" cy="38" r="5"/><path d="m21 13-10 20m16-20 10 20M13 38h22"/>',
'layers': '<path d="m24 4 20 12-20 12L4 16Zm-20 22 20 12 20-12M4 36l20 11 20-11"/>',
'clock': '<circle cx="24" cy="24" r="20"/><path d="M24 11v14l10 6"/>',
'check': '<circle cx="24" cy="24" r="21"/><path d="m12 24 8 8 16-17"/>',
'server': '<rect x="4" y="6" width="40" height="29" rx="4"/><path d="M24 35v8M14 43h20m-18-22 6 5 12-12"/>',
'bell': '<path d="M9 35h30l-5-8V17a10 10 0 0 0-20 0v10Zm10 7h10M24 1v3M3 13l5 3m37-3-5 3"/>',
'help': '<circle cx="24" cy="24" r="20"/><path d="M18 17a6 6 0 1 1 9 5c-3 2-3 4-3 6m0 6v1"/>',
'lock': '<rect x="9" y="21" width="30" height="23" rx="4"/><path d="M15 21V12a9 9 0 0 1 18 0v9M24 30v6"/>',
'download': '<path d="M24 3v27m-9-9 9 9 9-9M7 29v14h34V29"/>',
'upload': '<path d="M24 33V5m-9 10 9-10 9 10M7 29v14h34V29"/>',
'search': '<circle cx="20" cy="20" r="15"/><path d="m31 31 13 13"/>',
'filter': '<path d="M3 5h42L29 23v16l-10 5V23Z"/>',
'edit': '<path d="m6 33 1 10 10-1 28-28L34 3 6 33Zm23-24 11 11M20 43h25"/>',
'plus': '<path d="M24 5v38M5 24h38"/>',
'logout': '<path d="M21 6H5v36h16m11-9 10-9-10-9m10 9H17"/>',
'settings': '<circle cx="24" cy="24" r="7"/><path d="m19 3 10 0 2 8 8 1 5 9-6 6 2 8-9 6-7-4-7 4-9-6 2-8-6-6 5-9 8-1Z"/>'}
for name, body in paths.items():
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48"><g fill="none" stroke="#087f56" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>'
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(root / 'icons' / f'{name}.png'), output_width=96, output_height=96)
branch = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 220"><path d="M30 214C50 150 80 90 133 20" stroke="#79b493" stroke-width="3" fill="none"/><g fill="#9bc7a9"><path d="M62 144C19 133 6 101 9 76c31 11 51 28 53 68Z"/><path d="M78 115c16-48 44-65 77-62-14 40-39 60-77 62Z"/><path d="M94 88C63 65 64 35 65 17c29 17 38 42 29 71Z"/><path d="M47 175C14 168 4 148 2 130c29 4 41 15 45 45Z"/><path d="M60 160c27-31 47-32 74-23-24 29-49 31-74 23Z"/><path d="M113 57c-4-32 11-49 33-57-2 26-11 43-33 57Z"/></g></svg>'
cairosvg.svg2png(bytestring=branch.encode(), write_to=str(root / 'branch.png'), output_width=320, output_height=440)
