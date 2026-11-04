exec(compile(open('/work/demo/three-fields/explore.py').read(), '/work/demo/three-fields/explore.py', 'exec'))
replay(session)
Path('/work/.cps/three-field-demo/replay-session-end.json').write_text(json.dumps(session.status(),indent=2,default=lambda value:value.item())+'\n')
