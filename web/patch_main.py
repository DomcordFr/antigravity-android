#!/usr/bin/env python3
"""
web/patch_main.py - Dynamic patcher for web/main.js.

Locates the Appearance settings block and injects the Desktop Mode toggle
and native Android system theme detection if not already present.
Safe, idempotent, and resilient across upstream versions (v2.4.0 through v2.34.0).
"""

import sys
import os
import re

def patch_main(file_path):
    if not os.path.isfile(file_path):
        print(f"[web-patch] file not found: {file_path}", file=sys.stderr)
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    if "Desktop Mode" in content or "ag_desktop_mode" in content:
        print("[web-patch] Desktop Mode toggle already present in main.js")
        return True

    # 1. Locate Theme element in Appearance
    theme_idx = content.find('{label:"Theme"')
    if theme_idx == -1:
        print("[web-patch] {label:\"Theme\"} not found in main.js", file=sys.stderr)
        return False

    window_start = max(0, theme_idx - 1200)
    window_end = min(len(content), theme_idx + 1200)
    window_text = content[window_start:window_end]

    # 2. State hook injection pattern in Appearance component:
    # Matches:
    #   - 2.4/2.11: var C=g!==3,D=g!==2,E=F=>G=>{F===t&&v(G)};
    #   - 2.34.0:   B=b!==3;var D=b!==2;
    hook_pattern = re.compile(
        r'(var\s+[A-Za-z0-9_$]+=[A-Za-z0-9_$]+!==3,\s*[A-Za-z0-9_$]+=[A-Za-z0-9_$]+!==2,\s*[A-Za-z0-9_$]+=[A-Za-z0-9_$]+=>\s*[A-Za-z0-9_$]+=>\{.*?\};)|'
        r'([A-Za-z0-9_$]+=[A-Za-z0-9_$]+!==3;\s*var\s+[A-Za-z0-9_$]+=[A-Za-z0-9_$]+!==2;)'
    )
    hook_match = hook_pattern.search(window_text)

    # 3. JSX Theme element pattern:
    theme_pattern = re.compile(
        r'([A-Za-z0-9_$]+)\.createElement\(([A-Za-z0-9_$]+),\{label:"Theme",.*?onSelect:[A-Za-z0-9_$]+\}\)'
    )
    theme_match = theme_pattern.search(window_text)

    if not hook_match or not theme_match:
        print(f"[web-patch] patterns not matched: hook={bool(hook_match)}, theme={bool(theme_match)}", file=sys.stderr)
        return False

    react_id = theme_match.group(1)
    orig_hook = hook_match.group(0)

    injected_hook = (
        f"var [isDesktop,setIsDesktop]=(0,{react_id}.useState)(()=>{{"
        "try{if(window.Android&&typeof window.Android.isDesktopMode==='function')return window.Android.isDesktopMode();"
        "var s=localStorage.getItem('ag_desktop_mode');return s===null?!1:s==='true'}catch(_){return !1}});"
        f"var onDesktopToggle=(0,{react_id}.useCallback)(v=>{{"
        "setIsDesktop(v);try{localStorage.setItem('ag_desktop_mode',String(v));"
        "if(window.Android&&typeof window.Android.setDesktopMode==='function')window.Android.setDesktopMode(v)}catch(_){}},[]);"
        + orig_hook
    )

    # 4. Detect switch and setting item components
    item_comp = "OU" if "var OU=" in content else "v3"
    switch_comp = "RU" if "RU" in content else "dX"

    sw_m = re.search(r'rightElement:\s*[A-Za-z0-9_$]+\.createElement\(([A-Za-z0-9_$]+),\{checked:', content)
    if sw_m:
        switch_comp = sw_m.group(1)
    row_m = re.search(r'var\s+([A-Za-z0-9_$]+)=\(\{label:[A-Za-z0-9_$]+,description:[A-Za-z0-9_$]+,rightElement:', content)
    if row_m:
        item_comp = row_m.group(1)

    orig_theme = theme_match.group(0)
    injected_theme = (
        orig_theme
        + f',{react_id}.createElement({item_comp},{{label:"Desktop Mode",description:"Use desktop viewport and user agent for the workspace",'
        + f'rightElement:{react_id}.createElement({switch_comp},{{checked:isDesktop,onCheckedChange:onDesktopToggle}})}})'
    )

    # 5. Native Android Theme Detection Hook (replaces standalone prefers-color-scheme check)
    z0_pattern = re.compile(
        r'function\s+([A-Za-z0-9_$]+)\(\)\{return\s+typeof\s+window!==\"undefined\"&&window\.matchMedia\?window\.matchMedia\(\"\(prefers-color-scheme:\s*dark\)\"\)\.matches:!1\}'
    )
    z0_match = z0_pattern.search(content)
    if z0_match:
        z0_fn = z0_match.group(1)
        orig_z0 = z0_match.group(0)
        injected_z0 = (
            f"function {z0_fn}(){{try{{if(typeof window!==\"undefined\"&&window.Android&&typeof window.Android.getTheme===\"function\"){{"
            f"var _t=window.Android.getTheme();if(_t===\"dark\")return!0;if(_t===\"light\")return!1}}"
            f"if(typeof window!==\"undefined\"&&window.__AG_RESOLVED_THEME__){{"
            f"if(window.__AG_RESOLVED_THEME__===\"dark\")return!0;if(window.__AG_RESOLVED_THEME__===\"light\")return!1}}}}catch(_e){{}}"
            f"return typeof window!==\"undefined\"&&window.matchMedia?window.matchMedia(\"(prefers-color-scheme: dark)\").matches:!1}}"
        )
        content = content.replace(orig_z0, injected_z0, 1)

    content = content.replace(orig_hook, injected_hook, 1)
    content = content.replace(orig_theme, injected_theme, 1)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("[web-patch] Successfully patched Desktop Mode toggle into main.js (mobile by default, English)")
    return True

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "main.js")
    if not patch_main(path):
        sys.exit(1)
