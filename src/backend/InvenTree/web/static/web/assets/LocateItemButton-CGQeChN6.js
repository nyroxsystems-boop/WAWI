import{K as d,r as l,ab as r,an as p,ao as g,j as n}from"./index-Db7AGPIq.js";import{A as f}from"./ActionButton-Cv5j5I5R.js";import{a as h}from"./Filter-BgnAqEQC.js";import{u as v}from"./UsePlugins-BAQCKs7Q.js";/**
 * @license @tabler/icons-react v3.34.1 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */const x=[["path",{d:"M21 12h-8a1 1 0 1 0 -1 1v8a9 9 0 0 0 9 -9",key:"svg-0"}],["path",{d:"M16 9a5 5 0 1 0 -7 7",key:"svg-1"}],["path",{d:"M20.486 9a9 9 0 1 0 -11.482 11.495",key:"svg-2"}]],_=d("outline","radar","Radar",x);function k({stockId:o,locationId:i}){const e=v("locate"),[a,s]=l.useState(void 0);l.useEffect(()=>{a&&e?e.find(m=>m.key===a)||s(void 0):s(e[0]?.key??void 0)},[a,e]);const c=l.useMemo(()=>({plugin:{field_type:"choice",value:a,onValueChange:t=>{s(t)},choices:e.map(t=>({value:t.key,display_name:t.meta?.human_name??t.name}))},item:{hidden:!0,value:o},location:{hidden:!0,value:i}}),[o,i,e]),u=h({url:p(g.plugin_locate_item),method:"POST",title:r._({id:"px+tn2"}),fields:c,successMessage:r._({id:"AXn3rz"})});return!e||e.length===0||!o&&!i?null:n.jsxs(n.Fragment,{children:[u.modal,n.jsx(f,{icon:n.jsx(_,{}),variant:"outline",size:"lg",tooltip:r._({id:"px+tn2"}),onClick:u.open,tooltipAlignment:"bottom"})]})}export{k as L};
//# sourceMappingURL=LocateItemButton-CGQeChN6.js.map
