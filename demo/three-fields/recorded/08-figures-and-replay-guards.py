exec(compile(open('/work/demo/three-fields/explore.py').read(), '/work/demo/three-fields/explore.py', 'exec'))
figures(fields, baselines, {'tc11': trial_tc11, 'supp12': trial_supp12, 'supp10': trial_supp10})
before_guard = [snapshot(s.pipeline) for s in fields.values()]
for action in (lambda: initialize(session), lambda: finish(fields, baselines, {}, '')):
    try:
        action()
    except FileExistsError:
        print('Existing outputs preserved')
    else:
        raise AssertionError('Expected existing-output guard')
assert before_guard == [snapshot(s.pipeline) for s in fields.values()]
print('Same process:', session.status()['pid'], session.status()['started'])
