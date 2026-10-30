"""Maintainer policy for the bundled catalog; imported user packs are independent."""
from copy import deepcopy


def excluded_action(name):
    return isinstance(name,str) and '女仆' in name


def filter_config(config, removed=()):
    result=deepcopy(config)
    animations=result.get('animations',{})
    def keep(name):return isinstance(name,str) and name not in removed and not excluded_action(name)
    for pool in ('idle','turn','drag','clicks'):
        if pool in animations:animations[pool]=[name for name in animations[pool] if keep(name)]
    if not animations.get('idle'):
        raise ValueError('动画过滤后缺少待机动作')
    moves=animations.get('moves',{})
    if 'actions' in moves:moves['actions']=[action for action in moves['actions'] if keep(action.get('name'))]
    categories=[]
    for category in animations.get('categories',[]):
        category['actions']=[name for name in category.get('actions',[]) if keep(name)]
        if category['actions']:categories.append(category)
    if 'categories' in animations:animations['categories']=categories
    # Preserve event-band indexes when a future source clip is excluded.
    for event,bands in animations.get('events',{}).items():
        filtered=[]
        for band in bands:
            names=[name for name in (band if isinstance(band,list) else [band]) if keep(name)]
            filtered.append((names if isinstance(band,list) else names[0]) if names else animations['idle'][0])
        animations['events'][event]=filtered
    return result


def filter_manifest(manifest):
    blocked={key for key,clip in manifest['clips'].items() if excluded_action(key)
             or excluded_action(manifest.get('clipLabels',{}).get(key))
             or excluded_action(clip.get('source',{}).get('file'))}
    result=filter_config(manifest,blocked)
    result['clips']={key:clip for key,clip in result['clips'].items() if key not in blocked}
    result['clipLabels']={key:value for key,value in result.get('clipLabels',{}).items() if key not in blocked}
    result['libraryClips']=[key for key in result.get('libraryClips',result['clips']) if key not in blocked]
    result['idleMicroClips']=[key for key in result.get('idleMicroClips',[]) if key not in blocked]
    fallback=result['animations']['idle'][0]
    for key,value in result.get('stateMap',{}).items():
        if value in blocked:result['stateMap'][key]=fallback
    for mapping in ('workingActivityMap','dragMap'):
        if mapping in result:result[mapping]={key:value for key,value in result[mapping].items() if value not in blocked}
    source=result.setdefault('assetSource',{})
    source['excludedClips']=sorted(set(source.get('excludedClips',[]))|blocked)
    source['includedCount']=len(result['libraryClips'])
    return result,blocked
