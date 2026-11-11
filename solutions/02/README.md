# SATELLITE PASS SIMULATION (`solutions/O2`)

- ground station (`pass_runner.py`) communicates with a simulation satellite (`mock_pass.py`)

## Requirements

- Python 3.13 (stdlib only: `argparse`, `json`, `time`, `socket`, `datetime`, `logging`, `sys`)
- No other packages

## Files

```text
solutions/02/
├── README.md               # how to run the mock, the runner and the evidence
├── NOTES.md                # decisions, time model, gates, limits
├── PASS_SESSION.md         # procedure
├── mock_pass.py            # simulation satellite
├── pass_runner.py          # ground station
├── fixtures/
│   └── pass_plan.json      # scheduled activities
├── evidence_nominal/       # results of a successful run
│   ├── mock.log
│   ├── pass.log
│   ├── pass_report.json
│   ├── pass_report.md
│   └── README.md
└── evidence_degraded/      # results from an aborted run
    ├── mock.log
    ├── pass.log
    ├── pass_report.json
    ├── pass_report.md
    └── README.md
```	
## **How to run the project**

## 1st case (successful run)

- use **two command windows** opened directly from inside the `solutions/O2/` folder

### In the 1st terminal (simulated satellite):

- run: `python mock_pass.py --drop-rate 0 --max-elev 45 --log "mock.log"`

### In the 2nd terminal (ground station):

- run: `python pass_runner.py --plan fixtures/pass_plan.json --log pass.log --report-json pass_report.json --report-md pass_report.md`

#### Expected results: `PASS`

#### Exit code: `0`

- all scheduled activities were done succesfully and the required files were generated based on them

#### To reproduce evidence:

-run:
1. `python mock_pass.py --drop-rate 0 --max-elev 45 > evidence_nominal/mock.log`
2. `python pass_runner.py --plan fixtures/pass_plan.json --log evidence_nominal/pass.log --report-json evidence_nominal/pass_report.json --report-md evidence_nominal/pass_report.md`

---

## 2nd case (aborted run)

- use **two command windows** opened directly from inside the `solutions/O2/` folder

### In the 1st terminal (simulated satellite):

- run: `python mock_pass.py --max-elev 8 --log "mock.log"`

### In the 2nd terminal (ground station):

- run: `python pass_runner.py --plan fixtures/pass_plan.json --log pass.log --report-json pass_report.json --report-md pass_report.md`

#### Expected results: `ABORT`

#### Exit code: `2`

- the elevation doesnt reach more than 8 dergees, so it doesnt reach the required 10 degrees (`min_elev_deg`), therefore the transmission **aborts**

#### To reproduce evidence:

-run:
1. `python mock_pass.py --max-elev 8 > evidence_degraded/mock.log`
2. `python pass_runner.py --plan fixtures/pass_plan.json --log evidence_degraded/pass.log --report-json evidence_degraded/pass_report.json --report-md evidence_degraded/pass_report.md`

---

## Exit codes:

### `0` = Success

- everything was completed well

### `1` = Fail

- normal failure or protocol error happened

### `2` = Abort

- the state is not safe, preflight failed or window expired
