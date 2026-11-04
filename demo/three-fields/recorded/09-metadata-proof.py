metadata_proof = {}
for field, current in fields.items():
    metadata = {key: str(current.measurements.get_current_image_measurement('Metadata_' + key)) for key in ('Plate', 'Well', 'Site')}
    expected_metadata = json.loads((OUT/'expected.json').read_text())['fields'][field]['metadata']
    assert metadata == expected_metadata
    metadata_proof[field] = {'native_metadata': metadata, 'matches_expected': True, 'input_directory': current.input_dir}
write_json('metadata-proof.json', metadata_proof)
print(json.dumps(metadata_proof, indent=2))
