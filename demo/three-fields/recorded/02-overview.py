import matplotlib.pyplot as plt
fig, axes = plt.subplots(1, 3, figsize=(12, 4.3))
for ax, field in zip(axes, FIELDS):
    ax.imshow(plt.imread(OUT / 'views' / (field + '-baseline.png')))
    ax.set_title(field + ': ' + str(fields[field].counts()['NucleiIncludingEdges']) + ' primary nuclei')
    ax.axis('off')
fig.suptitle('Baseline: corrected DNA with IdentifyPrimaryObjects outlines')
fig.tight_layout()
fig.savefig(OUT / 'views' / 'baseline-overview.png', dpi=150)
plt.close(fig)
