import random
def boot_lo(a,b,tasks,draws=600,rng=random):
    ds=[]
    for _ in range(draws):
        pick=[rng.choice(tasks) for _ in tasks]
        sa=sum(a[t] for t in pick); sb=sum(b[t] for t in pick); n=5*len(pick)
        ds.append((sa-sb)/n)
    ds.sort(); return ds[int(.025*len(ds))]
def sim(p0, eff, het, sims=400, seed=1):
    rng=random.Random(seed); tasks=list(range(7)); hit=0
    for _ in range(sims):
        a={};b={}
        for t in tasks:
            e = eff*2 if (het and t%2==0) else (0 if het else eff)   # het: effect only in ~half the tasks (double size)
            pb=p0; pa=min(1,max(0,p0+e))
            b[t]=sum(rng.random()<pb for _ in range(5)); a[t]=sum(rng.random()<pa for _ in range(5))
        lo=boot_lo(a,b,tasks,rng=rng)
        t1=sum(a[t]>b[t] for t in range(4))
        if lo>0 and t1>=3: hit+=1
    return hit/sims
for p0 in (0.1,0.3):
    for eff in (0.2,0.4,0.6):
        print(f'p0={p0} eff=+{int(eff*100)}pp  homogeneous={sim(p0,eff,False):.2f}  half-tasks={sim(p0,eff/2,True):.2f}')
