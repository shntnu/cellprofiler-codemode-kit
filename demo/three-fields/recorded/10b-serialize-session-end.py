Path('/work/.cps/three-field-demo/original-session-end.json').write_text(json.dumps(end,indent=2,default=lambda value:value.item())+'\n')
print('Original process',end['session']['pid'],end['session']['started'])
