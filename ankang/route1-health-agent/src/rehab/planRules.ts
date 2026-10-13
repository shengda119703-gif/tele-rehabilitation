/** Curated starting variants. These are resource filters, never clinical clearance.
 * Keep all card conditions and source ranges; do not assign a numeric prescription.
 * Additional cards remain searchable until their variants can be mapped explicitly.
 */
export const starterRules = [
  {id:'T-LOW-046',regions:['踝'],level:0,equipmentAny:[['无轮稳固椅'],['稳固椅'],['硬床']],variant:'仅无外阻上下活动；不加入内外翻或负重。'},
  {id:'T-LOW-003',regions:['膝'],level:0,equipmentAny:[['无轮稳固椅'],['稳固椅']],variant:'仅徒手坐姿版本；负重与弹力带版本需另行核对。'},
  {id:'T-LOW-002',regions:['髋','膝'],level:0,equipmentAny:[['硬床','滑布'],['垫','滑布']],variant:'有脚跟滑布支持的卧位版本；先核对上下床和活动许可。'},
  {id:'T-LOW-017',regions:['髋','膝'],level:0,equipmentAny:[['无轮稳固椅'],['稳固椅']],variant:'仅无附加负重版本；椅高、扶手和负重许可须逐项核对。'},
  {id:'T-AXU-022',regions:['肩'],level:0,equipmentAny:[['稳定桌面']],variant:'仅桌面支撑版本；不自动升级墙面、角度或助力程度。'},
] as const;
