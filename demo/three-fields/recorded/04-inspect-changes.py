examples = [('A01_s1', 'tc11', 'split', 804, 783), ('A01_s2', 'tc11', 'split', 713, 136), ('A01_s2', 'tc11', 'merge', 126, 804), ('A01_s1', 'supp12', 'merge', 242, 257), ('A01_s2', 'supp12', 'merge', 247, 195), ('A02_s1', 'supp12', 'merge', 351, 945)]
fig, axes = plt.subplots(len(examples), 2, figsize=(7, 17))
example_records = []
for row, (field, name, kind, y, x) in enumerate(examples):
    s = fields[field]
    result = {'tc11': trial_tc11, 'supp12': trial_supp12}[name][field]
    crop = [max(0, y-70), min(1080, y+70), max(0, x-70), min(1080, x+70)]
    raw = s.view(objects=[], crop=crop, path=OUT/'views'/(field+'-'+name+'-'+kind+'-raw.png'))
    overlay = s.view(objects=[result], ref=baselines[field]['NucleiIncludingEdges'], crop=crop, path=OUT/'views'/(field+'-'+name+'-'+kind+'-comparison.png'))
    for col, item in enumerate((raw, overlay)):
        axes[row,col].imshow(plt.imread(item['path']))
        axes[row,col].axis('off')
    axes[row,0].set_title(field+' '+name+' '+kind+' near (y,x)=('+str(y)+','+str(x)+')', fontsize=10)
    axes[row,1].set_title('baseline red; candidate green; shared yellow', fontsize=9)
    example_records.append({'field':field,'candidate':name,'change':kind,'center_yx':[y,x],'crop_y0y1x0x1':crop,'raw':raw,'comparison':overlay})
fig.suptitle('Changed objects: corrected DNA (left), candidate vs baseline (right)', fontsize=11)
fig.tight_layout()
fig.savefig(OUT/'views'/'first-trials-crops.png', dpi=130)
plt.close(fig)
write_json('first-trials-crops.json', example_records)
