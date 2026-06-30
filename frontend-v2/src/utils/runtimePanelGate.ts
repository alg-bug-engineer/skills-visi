/** 运行数据面板揭示门控：须同时满足「运行数据步骤已开始」与「路口结构步骤已完成」。 */
export function shouldRevealRuntimePanel(
  dataFetchStarted: boolean,
  cognitionDone: boolean,
): boolean {
  return dataFetchStarted && cognitionDone
}
