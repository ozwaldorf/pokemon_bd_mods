"""Read field model geometry in prefab coordinates, including skin bind poses."""
import math
import re
import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler

def identity():
    return [[float(i == j) for j in range(4)] for i in range(4)]

def mul(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

def point(m, v):
    return [sum(m[i][j]*v[j] for j in range(3)) + m[i][3] for i in range(3)]

def vector(v):
    return [v[k] for k in ('x', 'y', 'z')]

def local(t):
    x,y,z,w = [t['m_LocalRotation'][k] for k in ('x','y','z','w')]
    r = [[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],
         [2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],
         [2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]]
    s = vector(t['m_LocalScale']); p = vector(t['m_LocalPosition'])
    return [[r[i][j]*s[j] for j in range(3)]+[p[i]] for i in range(3)]+[[0,0,0,1]]

def corners(bounds):
    c,e = vector(bounds['m_Center']), vector(bounds['m_Extent'])
    return [[c[i]+signs[i]*e[i] for i in range(3)]
            for signs in [(x,y,z) for x in (-1,1) for y in (-1,1) for z in (-1,1)]]

def tilt(v, angle):
    c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    return [v[0],c*v[1]-s*v[2],s*v[1]+c*v[2]]

def inspect(species, folder):
    FOLDER = folder
    candidates=sorted(p for p in (FOLDER/'field').glob(f'pm{species:04d}_*') if p.is_file() and p.name.endswith('_00'))
    if not candidates:return {'species':species,'error':'No non-shiny field model'}
    path=candidates[0]
    env=UnityPy.load(str(path))
    transforms={}; go={}; skins=[]
    for obj in env.objects:
        if obj.type.name=='Transform':transforms[obj.path_id]=obj.read_typetree()
        elif obj.type.name=='GameObject':go[obj.path_id]=obj.read_typetree()['m_Name']
        elif obj.type.name=='SkinnedMeshRenderer':skins.append((obj,obj.read_typetree()))
    cache={}
    def world(pid):
        if not pid:return identity()
        if pid not in cache:
            t=transforms[pid]
            if t['m_Father']['m_FileID']:raise ValueError('External transform parent')
            cache[pid]=mul(world(t['m_Father']['m_PathID']),local(t))
        return cache[pid]
    bones={go[t['m_GameObject']['m_PathID']]:point(world(pid),[0,0,0]) for pid,t in transforms.items()}
    # Mesh bounds are in authoring coordinates. The first bone's current
    # transform times its inverse bind pose carries them into the field prefab.
    # Check all bones agree before using that single affine transform.
    meshes={}
    for candidate in (FOLDER/'common').glob(f'pm{species:04d}_*'):
        ce=UnityPy.load(str(candidate))
        for obj in ce.objects:
            if obj.type.name=='Mesh':meshes[(obj.assets_file.name,obj.path_id)]=(obj,obj.read_typetree())
    allpoints=[]; corepoints=[]; torsopoints=[]; disagreements=[]; sources=[]
    for obj,skin in skins:
        ptr=skin['m_Mesh'];cab=obj.assets_file.name if ptr['m_FileID']==0 else obj.assets_file.externals[ptr['m_FileID']-1].name
        resolved=meshes.get((cab,ptr['m_PathID']))
        if resolved is None:raise ValueError(f'Missing mesh {cab}/{ptr["m_PathID"]}')
        meshobj,mesh=resolved
        matrices=[]; bone_names=[]
        for bone,bind in zip(skin['m_Bones'],mesh['m_BindPose']):
            if bone['m_FileID'] or bone['m_PathID'] not in transforms:
                raise ValueError('Unresolved skin bone; cannot preserve vertex bone indices')
            matrices.append(mul(world(bone['m_PathID']),[[bind[f'e{i}{j}'] for j in range(4)] for i in range(4)]))
            bone_names.append(go[transforms[bone['m_PathID']]['m_GameObject']['m_PathID']])
        if not matrices:raise ValueError('No resolved bind poses')
        m=matrices[0]
        disagreement=max(abs(other[i][j]-m[i][j]) for other in matrices for i in range(4) for j in range(4))
        disagreements.append(disagreement)
        handler=MeshHandler(meshobj.read());handler.process()
        pts=[]
        for vertex,indices,weights in zip(handler.m_Vertices,handler.m_BoneIndices,handler.m_BoneWeights):
            if disagreement>0.02:
                transformed=[0.0,0.0,0.0]
                for index,weight in zip(indices,weights):
                    if not weight:continue
                    pv=point(matrices[index],vertex)
                    for axis in range(3):transformed[axis]+=weight*pv[axis]
            else:transformed=point(m,vertex)
            pts.append(transformed)
            torso_weight=sum(weight for index,weight in zip(indices,weights)
                if weight and re.fullmatch(r'(Waist|Hips|Spine\d*|Chest|Neck\d*|Body\d*)',bone_names[index]))
            head_weight=sum(weight for index,weight in zip(indices,weights)
                if weight and re.fullmatch(r'Head\d*',bone_names[index]))
            if torso_weight>=0.5:torsopoints.append(transformed)
            if torso_weight+head_weight>=0.5:corepoints.append(transformed)
        if not pts:pts=[point(m,c) for c in corners(mesh['m_LocalAABB'])]
        allpoints.extend(pts)
        sources.append(mesh['m_Name'])
    if not allpoints:raise ValueError('No mesh bounds')
    low=[min(p[i] for p in allpoints) for i in range(3)]
    high=[max(p[i] for p in allpoints) for i in range(3)]
    dims=[high[i]-low[i] for i in range(3)]
    waist=bones.get('Waist',bones.get('Hips',[0,(low[1]+high[1])/2,0]))
    head=bones.get('Head',bones.get('Head1'))
    upper=bones.get('Spine2',bones.get('Neck',head))
    delta=[upper[i]-waist[i] for i in range(3)] if upper else [0,dims[1],0]
    if sum(v*v for v in delta)<0.002 and head:delta=[head[i]-waist[i] for i in range(3)]
    if sum(v*v for v in delta)<0.002 and 'LFoot' in bones and 'RFoot' in bones:
        # Registeel's Head and Waist pivots coincide. Paired feet reveal its
        # upright torso without confusing Geodude's round, floating body.
        feet=[(bones['LFoot'][i]+bones['RFoot'][i])/2 for i in range(3)]
        delta=[waist[i]-feet[i] for i in range(3)]
    angle=math.degrees(math.atan2(abs(delta[1]),max(0.00001,math.hypot(delta[0],delta[2]))))
    # Width alone mistakes outstretched arms and crab claws for a flat disc.
    # The star rigs expose three head branches instead of a single head.
    flat=all(k in bones for k in ('Head1','Head2','Head3')) and 'Head' not in bones
    if flat:posture='upright disc';pitch=-85
    elif angle>=50:posture='upright body';pitch=35 if 'LFoot' in bones else 20
    elif angle>=25:posture='inclined body';pitch=20
    else:posture='horizontal body';pitch=0
    haslegs='LFoot' in bones and 'RFoot' in bones
    if flat:anatomy='star disc'
    elif any(k in bones for k in ('LFoot2','LLeg2')):anatomy='multi-legged'
    elif haslegs:
        anatomy='quadruped' if angle<25 else 'biped'
        # Low front feet indicate a horizontal body even with a raised neck.
        if 'LHand' in bones and abs(bones['LHand'][1]-bones['LFoot'][1])<0.18*dims[1] and angle<60:
            anatomy='quadruped';posture='horizontal body';pitch=0
    elif 'LFoot' not in bones and sum(bool(re.fullmatch(r'Tail\d+',k)) for k in bones)>=5:anatomy='serpentine'
    elif angle<25:anatomy='fish or low body'
    else:anatomy='upright aquatic or unusual'
    # A torso midpoint is more useful for rider alignment than the head or
    # full silhouette center (which is displaced by tails, wings and horns).
    seat=[waist[i]+0.3*(upper[i]-waist[i]) for i in range(3)] if upper else waist
    core=torsopoints if len(torsopoints)>=30 else corepoints
    core_source='torso skin weights' if len(torsopoints)>=30 else 'torso/head skin weights'
    if len(core)<30:core=allpoints;core_source='whole mesh fallback'
    def quantile(values,fraction):
        values=sorted(values)
        return values[round((len(values)-1)*fraction)]
    core_low=[quantile([p[i] for p in core],0.01) for i in range(3)]
    core_high=[quantile([p[i] for p in core],0.99) for i in range(3)]
    core_dims=[max(0.01,core_high[i]-core_low[i]) for i in range(3)]
    # Use an actual torso surface near the saddle bone, rather than the full
    # silhouette or bone center. Flowers, arms and tails can distort either.
    centered=[p for p in core if abs(p[0]-seat[0])<=core_dims[0]*0.25]
    if posture=='horizontal body' or anatomy=='multi-legged':
        band=[p for p in centered if abs(p[2]-seat[2])<=core_dims[2]*0.25]
        if band:seat[1]=quantile([p[1] for p in band],0.95)
    else:
        band=[p for p in centered if abs(p[1]-seat[1])<=core_dims[1]*0.2]
        if band:seat[2]=quantile([p[2] for p in band],0.1)
    return {'species':species,'model':path.name,
            'dimensions':dims,'minimum':low,'maximum':high,'posture':posture,'body_axis_degrees':angle,
            'suggested_pitch':pitch,'anatomy':anatomy,'seat':seat,'bone_positions':bones,
            'core_dimensions':core_dims,'core_minimum':core_low,'core_maximum':core_high,
            'core_source':core_source,'core_vertex_count':len(core),
            'mesh_names':sources,'bind_matrix_max_disagreement':max(disagreements)}
