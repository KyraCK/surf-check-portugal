"""Selbst gezeichnete Strichsymbole (24 x 24) für Wetter, Wellen und Gezeiten.

Alle Symbole sind eigene Zeichnungen und liegen unter derselben Lizenz wie das Projekt.
"""

ICONS = {
    "wave": '<path d="M2 9c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 4.4-3 6.8 0"/><path d="M2 15c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 4.4-3 6.8 0"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.1"/>',
    "warn": '<path d="M12 3.8l9.2 16H2.8z"/><path d="M12 10v4.6M12 17.4v.1"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
    "cloud": '<path d="M7 18.5h9.5a4 4 0 0 0 .5-7.97A5.5 5.5 0 0 0 6.4 9.6 4.5 4.5 0 0 0 7 18.5z"/>',
    "partly": '<circle cx="8" cy="8" r="2.6"/><path d="M8 2.6v1.3M2.6 8h1.3M4.2 4.2l.9.9M11.8 4.2l-.9.9"/><path d="M10 20h7.5a3.5 3.5 0 0 0 .4-6.97A4.8 4.8 0 0 0 9 13.2 3.4 3.4 0 0 0 10 20z"/>',
    "rain": '<path d="M7 15.5h9.5a4 4 0 0 0 .5-7.97A5.5 5.5 0 0 0 6.4 6.6 4.5 4.5 0 0 0 7 15.5z"/><path d="M8.5 18.5l-1 2.5M12.5 18.5l-1 2.5M16.5 18.5l-1 2.5"/>',
    "arrow": '<path d="M12 20V5M6.5 10.5L12 5l5.5 5.5"/>',
    "period": '<path d="M3 9c2.2-5 4.4-5 6.6 0s4.4 5 6.6 0 3-3 4.8-1"/><path d="M3 18h13.6M5.2 16L3 18l2.2 2M14.4 16l2.2 2-2.2 2"/>',
    "tidelow": '<path d="M2 12c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 4.4-3 6.8 0"/><path d="M12 3v10M8.5 9.5L12 13l3.5-3.5"/><path d="M2 20c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 4.4-3 6.8 0" opacity=".5"/>',
    "swim": '<circle cx="17" cy="6" r="2"/><path d="M6 14l4.5-4.2 4 2.2"/><path d="M3 18c2-2.2 4-2.2 6 0s4 2.2 6 0 4-2.2 6 0"/>',
    "trail": '<path d="M6 21c-2.5-3.5 2.5-5.5 4.5-7s2-3.5-.5-4.5S7.500 6.500 10 4.500"/><circle cx="17.500" cy="5" r="1.300"/><path d="M14 21c1.200-3 4.800-3 6-6"/>',
    "tree": '<path d="M12 21v-5"/><path d="M12 3l5 7h-2.500l4 6H5.500l4-6H7z"/>',
    "lighthouse": '<path d="M9 21l1.500-12h3L15 21z"/><path d="M10 9l2-4 2 4"/><path d="M5 7l3 1M19 7l-3 1M6.500 3l2.500 2M17.500 3L15 5"/>',
    "city": '<path d="M3 21V10l5-3 5 3v11"/><path d="M13 21V6l4-2 4 2v15"/><path d="M6 14h4M6 17h4M16 10h2M16 14h2M16 18h2"/>',
    "tidehigh": '<path d="M2 19c2.2-3 4.4-3 6.6 0s4.4 3 6.6 0 4.4-3 6.8 0"/><path d="M12 14V4M8.5 7.5L12 4l3.5 3.5"/>',
    "ruler": '<rect x="2.5" y="8" width="19" height="8" rx="1.8"/><path d="M7 8v3M11 8v4M15 8v3M19 8v3"/>',
    "mountain": '<path d="M2.5 19.5l6.5-11 4 6.5 2.5-4 6 8.5z"/>',
    "castle": '<path d="M4 20V9h3v2h2.5V9h5v2H17V9h3v11z"/><path d="M10.5 20v-4a1.5 1.5 0 0 1 3 0v4"/>',
    "ext": '<path d="M8 16L18 6M10 6h8v8"/>',
}


def icon_definitionen() -> str:
    """Alle Symbole als ein versteckter SVG-Block, der einmal pro Seite eingefügt wird."""
    inner = "".join(
        f'<symbol id="i-{n}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round">{d}</g></symbol>'
        for n, d in ICONS.items()
    )
    return f'<svg width="0" height="0" style="position:absolute" aria-hidden="true">{inner}</svg>'
