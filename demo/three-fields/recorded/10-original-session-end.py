end = {'session': session.status(), 'fields': {}}
for name, current in fields.items():
    end['fields'][name] = {'status':current.status(), 'metadata':{key:str(current.measurements.get_current_image_measurement('Metadata_'+key)) for key in ('Plate','Well','Site')}}
Path('/work/.cps/three-field-demo/original-session-end.json').write_text(json.dumps(end,indent=2)+'\n')
print(json.dumps({'pid':end['session']['pid'],'started':end['session']['started'],'counts':{name:entry['status']['object_counts'] for name,entry in end['fields'].items()}},indent=2))
