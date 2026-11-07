# Core modelling examples

These upstream examples are JSON inputs to the separately installed runtime, not a claim that a live build has been tested on this machine. Choose a new dedicated layer if these names are already in use.


Table, 1.6 x 0.8 m:
```json
{"units":"m","layer":"Tavolo","clear":true,"parts":[
 {"type":"box","name":"piano","at":[0,0,0.72],"size":[1.6,0.8,0.04]},
 {"type":"array","of":{"type":"box","name":"gamba","at":[0.05,0.05,0],"size":[0.05,0.05,0.72]},"n":[2,2,1],"step":[1.45,0.65,0]}]}
```

Two-storey house, 10 x 6 m, windows on the long side:
```json
{"units":"m","layer":"Casa","clear":true,"parts":[{"type":"building","name":"casa","footprint":[[0,0],[10,0],[10,6],[0,6]],
 "floors":2,"floor_h":3,"roof":"gable","roof_h":2.5,
 "openings":[{"wall":0,"offset":1,"width":1.2,"height":1.4,"sill":0.9,"count":3,"gap":1.8},{"wall":2,"offset":4.4,"width":1.2,"height":2.2,"sill":0,"floor":0}]}]}
```

Vase:
```json
{"units":"cm","layer":"Vaso","clear":true,"parts":[{"type":"revolve","profile":[[0,0],[6,0],[9,10],[5,22],[6,25],[0,25]]}]}
```
