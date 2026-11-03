// AIの思考を画面とは別のスレッドで行う（docs/play.html から使う。web/play_local.js の runJob を呼ぶだけ）。
"use strict";
importScripts("play_data.js", "carcassonne_engine.js", "play_local.js");
const ENGINE = new self.Carcassonne.Engine(self.PLAY_DATA.tables);
self.onmessage = e => {
  try {
    const result = self.CarcassonneLocal.runJob(ENGINE, self.PLAY_DATA, e.data);
    self.postMessage({ id: e.data.id, result });
  } catch (err) {
    self.postMessage({ id: e.data.id, error: String(err && err.message ? err.message : err) });
  }
};
