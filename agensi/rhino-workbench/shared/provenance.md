# Provenance, licence and scope

Package: Rhino Workbench 0.2.0, a pack of three skills (rhino-model, rhino-facade, rhino-doctor), November 2026. Author: Filippo Antonio Visentin.
Source: https://github.com/filippovisentin/claude-rhino-plugin (MIT), folder `agensi/rhino-workbench`, matching the runtime of the same commit.

The schema, recipes, architectural anatomy, dimension defaults and diagnostics come from that repository's own skills. This pack is MIT too; the licence does not change because the instructions are sold through Agensi.

Not included: runtime code, executables, Python environments, MCP configuration, datasets or trained weights. The runtime's detector weights are restricted to the author's studio and are not licensed by this pack.

Tested before release on four annotated CMP facades, each read by two agents of the same model: one with the plugin's own skill, one with these instructions. Mean overlap per element class, plugin / pack: 0.79 / 0.81, 0.65 / 0.59 (whole building), 0.59 / 0.61, 0.43 / 0.51; on average 0.62 / 0.63. One agent with only this pack also modelled and built a whole building on its own through `run_python` (level 2): 410 solids, all valid and closed. That is parity on these photos, not a guarantee of accuracy on others; a model from a photo is not a survey.
