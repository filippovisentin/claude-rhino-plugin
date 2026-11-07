# Provenance, licence and scope

Package: Rhino Workbench 0.2.0, a pack of three skills (rhino-model, rhino-facade, rhino-doctor), November 2026. Author: Filippo Antonio Visentin.
Source: https://github.com/filippovisentin/claude-rhino-plugin (MIT), folder `agensi/rhino-workbench`, matching the runtime of the same commit.

The schema, recipes, architectural anatomy, dimension defaults and diagnostics come from that repository's own skills. This pack is MIT too; the licence does not change because the instructions are sold through Agensi.

Not included: runtime code, executables, Python environments, MCP configuration, datasets or trained weights. The runtime's detector weights are restricted to the author's studio and are not licensed by this pack.

Tested before release: two photos read by two agents of the same model, one with the plugin's own skill and one with these instructions, scored against annotated facades and built in Rhino 8 (all solids valid and closed). The scores were within a few points of each other (mean overlap per element class 0.63-0.81). That is evidence of parity on those photos, not a guarantee of accuracy on others; a model from a photo is not a survey.
