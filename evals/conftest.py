"""pytest in evals/: the tests of the scripts, not a run's copies or the fixture."""

# results/ holds each run's copy of the skills (their tests included) and the run's
# workspaces; fixture/ is the demo repo the cases start from, with its own test script.
collect_ignore = ["results", "fixture"]
