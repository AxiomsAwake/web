(()=>{'use strict';
const feedback=globalThis.AxiomsPlayerFeedback;
if(!feedback)return;
const text=id=>document.getElementById(id)?.textContent?.trim()||'—';
const value=id=>document.getElementById(id)?.value||'—';
function collectState(){
  const layers=[...document.querySelectorAll('input[data-layer]')].filter(input=>input.checked).map(input=>input.dataset.layer);
  const inspector=document.getElementById('inspector-content');
  const selected=inspector&&!inspector.hidden
    ? `${text('cell-coordinate')} · ${text('cell-terrain')} · elev ${text('cell-elevation')} · temp ${text('cell-temperature')} · pollution ${text('cell-pollution')} · clouds ${text('cell-clouds')} · wind ${text('cell-wind')}`
    : 'none';
  return {
    applicationVersion:'2.2.0',
    stage:text('stage-label'),
    generation:text('generation-label'),
    terrainBuild:text('build-label'),
    seed:value('seed-input'),
    pollutionRise:value('pollution-input'),
    speed:value('speed-select'),
    runControl:text('run-button'),
    visibleLayers:layers,
    selectedCell:selected,
    terrainMix:`ice ${text('mix-ice')} · water ${text('mix-water')} · ground ${text('mix-ground')} · forest ${text('mix-forest')} · city ${text('mix-city')}`,
    sky:`clear ${text('stat-clear')} · cloudy ${text('stat-cloudy')} · raining ${text('stat-raining')}`,
    signals:`pollution ${text('stat-pollution')} · temperature ${text('stat-temperature')} · wind ${text('stat-wind')}`
  };
}
const host=document.querySelector('.secondary-actions');
if(host)feedback.installFeedbackButton({
  game:'EarthSim',site:'earth-sim',host,className:'button button-quiet',build:'v2.2.0',buildInfoUrl:false,getState:collectState
});
})();
