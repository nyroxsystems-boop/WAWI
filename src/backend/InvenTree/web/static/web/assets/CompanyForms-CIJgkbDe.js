import{K as i,r as n,j as e}from"./index-Db7AGPIq.js";import{I as o}from"./IconAt-rYwKGkPn.js";import{aq as c,M as u,ar as l,I as p,al as f}from"./ThemeContext-CxdCkKtz.js";/**
 * @license @tabler/icons-react v3.34.1 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */const d=[["path",{d:"M7 9a4 4 0 1 0 8 0a4 4 0 0 0 -8 0",key:"svg-0"}],["path",{d:"M5.75 15a8.015 8.015 0 1 0 9.25 -13",key:"svg-1"}],["path",{d:"M11 17v4",key:"svg-2"}],["path",{d:"M7 21h8",key:"svg-3"}]],m=i("outline","globe","Globe",d);/**
 * @license @tabler/icons-react v3.34.1 - MIT
 *
 * This source code is licensed under the MIT license.
 * See the LICENSE file in the root directory of this source tree.
 */const v=[["path",{d:"M13 20l7 -7",key:"svg-0"}],["path",{d:"M13 20v-6a1 1 0 0 1 1 -1h6v-7a2 2 0 0 0 -2 -2h-12a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h7",key:"svg-1"}]],h=i("outline","note","Note",v);function g({manufacturerId:a,manufacturerPartId:r,partId:t}){return n.useMemo(()=>({part:{value:t,disabled:!!t,filters:{part:t,purchaseable:!0,active:!0}},manufacturer_part:{value:r,filters:{manufacturer:a,part_detail:!0,manufacturer_detail:!0},adjustFilters:s=>({...s.filters,part:s.data.part})},supplier:{filters:{active:!0,is_supplier:!0}},SKU:{icon:e.jsx(f,{})},description:{},link:{icon:e.jsx(p,{})},note:{icon:e.jsx(h,{})},pack_quantity:{},packaging:{icon:e.jsx(l,{})},active:{}}),[a,r,t])}function j(){return n.useMemo(()=>({part:{},manufacturer:{filters:{active:!0,is_manufacturer:!0}},MPN:{},description:{},link:{}}),[])}function y(){return{name:{},description:{},website:{icon:e.jsx(m,{})},currency:{icon:e.jsx(u,{})},phone:{icon:e.jsx(c,{})},email:{icon:e.jsx(o,{})},tax_id:{},is_supplier:{},is_manufacturer:{},is_customer:{},active:{}}}export{j as a,y as c,g as u};
//# sourceMappingURL=CompanyForms-CIJgkbDe.js.map
