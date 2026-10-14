/* UI 아이콘은 외부 폰트/네트워크 없이 단일 HTML에서도 표시합니다. */
function pharmacyUiIcon(name){
 const paths={search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',phone:'<path d="M5 3h4l2 5-3 2a15 15 0 0 0 6 6l2-3 5 2v4a2 2 0 0 1-2 2C9 20 4 15 3 5a2 2 0 0 1 2-2Z"/>',map:'<path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2Z M9 3v16 M15 5v16"/>',moon:'<path d="M20 13a8 8 0 0 1-9-9A9 9 0 1 0 20 13Z"/>',download:'<path d="M12 3v12m-4-4 4 4 4-4M4 15v5h16v-5"/>',chevron:'<path d="m9 5 7 7-7 7"/>',left:'<path d="m15 5-7 7 7 7"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>',reset:'<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6"/>',info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',layers:'<path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5"/>',print:'<path d="M7 8V3h10v5M7 17H3V8h18v9h-4M7 14h10v7H7Zm10-3h.01"/>',focus:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',plus:'<path d="M12 5v14M5 12h14"/>'};
 return `<svg class="ui-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.info}</svg>`;
}

/* 격자 대표점은 지도상 반경 32m로 확대합니다. 작은 축척에서만 최소 크기를 보장합니다.
   약국 기호는 면적이 아닌 위치를 뜻하므로 확대 단계에 맞춰 읽기 쉬운 크기로 키웁니다. */
function pharmacyGridPointRadius(zoom,latitude){
 const metresPerPixel=40075016.686*Math.cos(latitude*Math.PI/180)/(256*Math.pow(2,zoom));
 return Math.max(1.4,32/metresPerPixel);
}
function pharmacyMapPointSize(zoom,kind='normal'){
 const step=Math.max(0,Math.min(8,zoom-11));
 return kind==='candidate'?24+step*2:kind==='public'?8+step*1.4:4.5+step*1.1;
}
function pharmacyMapPinIcon(kind,zoom){
 const size=kind==='candidate'?pharmacyMapPointSize(zoom,kind):pharmacyMapPointSize(zoom,'public')*2;
 return L.divIcon({className:'pharmacy-map-pin',html:`<span class="${kind==='candidate'?'candidate-pin':'public-pin'}">${pharmacyUiIcon('plus')}</span>`,iconSize:[size,size],iconAnchor:[size/2,size/2],popupAnchor:[0,-size/2]});
}
