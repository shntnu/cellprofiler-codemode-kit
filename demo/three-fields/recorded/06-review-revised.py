fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(OUT/'views'/'first-trials-crops.png', dpi=130)
revised = json.loads((OUT/'supp10.json').read_text())
locations = revised['fields']['A01_s2']['measurement']['vs_ref']['merge_at']
fig, axes = plt.subplots(3, 4, figsize=(12, 9))
revised_views = []
for i, (y,x) in enumerate(locations):
    row, col = i//2, 2*(i%2)
    crop = [max(0,y-70), min(1080,y+70), max(0,x-70), min(1080,x+70)]
    raw = fields['A01_s2'].view(objects=[], crop=crop, path=OUT/'views'/('A01_s2-supp10-merge'+str(i)+'-raw.png'))
    overlay = fields['A01_s2'].view(objects=[trial_supp10['A01_s2']],ref=baselines['A01_s2']['NucleiIncludingEdges'],crop=crop,path=OUT/'views'/('A01_s2-supp10-merge'+str(i)+'-comparison.png'))
    for k,item in enumerate((raw,overlay)):
        axes[row,col+k].imshow(plt.imread(item['path']))
        axes[row,col+k].axis('off')
    axes[row,col].set_title('DNA at (y,x)=('+str(y)+','+str(x)+')',fontsize=10)
    axes[row,col+1].set_title('red baseline; green trial; yellow shared',fontsize=8)
    revised_views.append({'center_yx':[y,x],'crop_y0y1x0x1':crop,'raw':raw,'comparison':overlay})
fig.suptitle('Milder suppression 10: all six reported merges in dense field A01_s2',fontsize=13)
fig.tight_layout(rect=(0,0,1,.96))
fig.savefig(OUT/'views'/'revised-trial-crops.png',dpi=150)
plt.close(fig)
write_json('revised-trial-crops.json',revised_views)
