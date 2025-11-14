## BCN Nuke 16 Multi‑Shot Tools

This repository contains an artist‑friendly toolset for Nuke 16’s native multishot / Graph Scope Variable (GSV) workflow, built by **BCN Visuals** and **George Antonopoulos**.

The core UI is the **Switch Manager** panel, which lets you:

- **Define variants** (e.g. `screens`, `version`, `renderPass`) as GSV list variables.
- **Edit options** for each variant (e.g. individual screen names).
- **Sync** those options back to the root GSV.
- **Build VariableGroups** per option.
- **Create VariableSwitch nodes** wired to those variants.
- **Wrap Write/Group nodes** in VariableGroups so renders are scoped by the active variant.

This project is released under a **custom non‑commercial, attribution‑required license**. See `LICENSE` for full terms.

---

## Installation

1. **Clone or copy the repo**

   Place the folder somewhere on disk that Nuke can see, for example:

   - On macOS: `/Users/<you>/.nuke/BCN_Multishot_Toolset`
   - On Windows: `C:\Users\<you>\.nuke\BCN_Multishot_Toolset`

2. **Add the folder to `NUKE_PATH` (optional if inside `.nuke`)**

   If you put the repo **inside** your `.nuke` folder, Nuke will automatically pick up `init.py` and `menu.py`.

   If you keep it elsewhere, add the path to `NUKE_PATH` in your `.nuke/init.py`:

   ```python
   import nuke
   import os

   repo_path = os.path.expanduser("~/path/to/BCN_Multishot_Toolset")
   if repo_path not in nuke.pluginPath():
       nuke.pluginAddPath(repo_path)
   ```

   Make sure both `init.py` and `menu.py` from this repo are reachable via `NUKE_PATH`.

3. **Restart Nuke**

   After restarting, Nuke should load:

   - `init.py` (which adds `./nuke_tools` to the plugin path).
   - `menu.py` (which registers the Switch Manager panel and menu entries).

---

## Accessing the Switch Manager Panel

In Nuke’s GUI:

- Open the panel from **Pane → Switch Manager**, or
- Use the menu entry **Nuke → BCN Multishot → Switch Manager**.

The panel can be docked like any other Nuke pane and will remember its layout using the panel IDs:

- `uk.co.bcn.multishot.switch_manager` (current)
- `uk.co.bcn.multishot.screens_manager` (legacy, for old layouts)

---

## Quick Tutorial

### 1. Create a variant and options

1. Open the **Switch Manager** panel.
2. In the first section:
   - Set **Variant name** to something like `versions`.
   - In the option rows, enter your version names (e.g. `A`, `B`, `C`).
3. Use the **Current** dropdown to choose the default option.

You can add more variants (e.g. `screens`, `carpaint`) with the **+ Add Variant** button. Each variant gets its own section and options.

### 2. Sync variants to GSV

1. When your variants and options look correct, click **Sync Options to GSV**.
2. The panel will:
   - Create or update list‑type variables on the root `Gsv_Knob` (e.g. `__default__.screens`).
   - Ensure a GSV set per option for convenience.
3. After syncing, the sections are locked and the status line shows **“GSV synced ✓”**.
4. To edit again, click **Edit GSV** to unlock the sections; when finished, press **Sync Options to GSV** again.

### 3. Build VariableGroups per option

For any variant section:

1. Click **Build VariableGroups**.
2. The tool will:
   - Create a `VariableGroup` per option (e.g. `version_A`, `version_B` for the `versions` variant).
   - Set the group’s local GSV value for `__default__.<variant>` to that option (e.g. `__default__.versions = "Moxy"`).

Use these VariableGroups to host per‑screen overrides, formats, and other contextual logic.

### 4. Create a VariableSwitch preview

For any variant section:

1. Click **Create VariableSwitch**.
2. The tool will:
   - Create a `VariableSwitch` node.
   - Wire its `variable` knob to the chosen variant (e.g. `__default__.versions`).
   - Spawn input `Dot` nodes and connect them to the switch, one per option.
   - Populate the switch’s patterns with your option names.

You can connect different image streams to each input `Dot` and drive the active branch via the variant in the Variables panel.

### 5. Wrap a Write node in a VariableGroup

To lock a Write (or publish‑ready Group) to the current variant selections:

1. Select the **Write** node (or compatible Group) in the DAG.
2. In the Switch Manager panel, click **Lock Write node to Options**.
3. The helper will:
   - Insert a new `VariableGroup` just upstream of the selected node.
   - Rewire the input so the VariableGroup sits inline in the DAG.
   - Set each `__default__.<variant>` value on the group’s local `gsv` based on the panel’s current selections.

From then on, you can use Nuke’s native **VariableGroup UI** on that wrapper to control which variant context is active for renders, without modifying the internal Write node.

---

## License and Attribution

This toolset is provided under a **non‑commercial, attribution‑required license**:

- You may **use and modify** the tools in personal, studio, or freelance pipelines.
- Any redistribution or fork **must** clearly credit **BCN Visuals**, and keep this license.
- The tools and any derivatives **cannot be sold or turned into a paid/monetized product** or subscription.

See `LICENSE` for the exact wording.


