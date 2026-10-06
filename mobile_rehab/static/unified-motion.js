/* React Bits Rubber Segment / Prompt Bar interaction adaptation.
 * https://reactbits.dev/c/micro/rubber-segment
 * Existing links/forms own every action; no new gestures or fake stop action.
 */
(() => {
  const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  let thumb,active,animation;
  function selectNavigation() {
    const nav=document.querySelector('#nav'),item=nav.querySelector('[aria-current="page"]');
    if(!item||nav.hidden)return;
    if(!thumb){thumb=document.createElement('span');thumb.className='nav-thumb';thumb.setAttribute('aria-hidden','true');nav.prepend(thumb);}
    const next={left:item.offsetLeft,top:item.offsetTop,width:item.offsetWidth,height:item.offsetHeight};
    if(active===item&&Object.entries(next).every(([k,v])=>thumb.style[k]===v+'px'))return;
    const before=thumb.getBoundingClientRect(),container=nav.getBoundingClientRect();
    animation?.cancel();
    const frame=r=>Object.fromEntries(Object.entries(r).map(([k,v])=>[k,v+'px']));
    Object.assign(thumb.style,frame(next));
    if(active&&active!==item&&!reduced()){
      const prev={left:before.left-container.left,top:before.top-container.top,width:before.width,height:before.height};
      const bridge={left:Math.min(prev.left,next.left),top:Math.min(prev.top,next.top),
        width:Math.max(prev.left+prev.width,next.left+next.width)-Math.min(prev.left,next.left),
        height:Math.max(prev.top+prev.height,next.top+next.height)-Math.min(prev.top,next.top)};
      animation=thumb.animate([{...frame(prev),offset:0},{...frame(bridge),offset:.38},
        {...frame(next),transform:'scale(.97,1.035)',offset:.8},{...frame(next),transform:'scale(1)',offset:1}],
        {duration:320,easing:'cubic-bezier(.23,1,.32,1)'});
    }
    active=item;
  }
  function decorate(page){
    document.body.dataset.page=page;selectNavigation();
    const draft=document.querySelector('#draft'),composer=document.querySelector('.composer');
    if(draft&&composer&&!draft.dataset.motionDecorated){
      const update=()=>{composer.dataset.charged=String(Boolean(draft.value.trim()));};
      draft.dataset.motionDecorated='true';draft.addEventListener('input',update);update();
    }
    if(page==='home'){
      const content=document.querySelector('#content'),hero=content.querySelector('.hero');
      if(hero&&!content.querySelector('.home-layout')){
        const layout=document.createElement('div'),today=document.createElement('section');layout.className='home-layout';today.className='today-panel';
        while(hero.nextSibling)today.append(hero.nextSibling);layout.append(hero,today);content.append(layout);
      }
    }
  }
  addEventListener('resize',()=>{active=null;selectNavigation();});
  window.ProductMotion={selectNavigation,decorate};
})();
