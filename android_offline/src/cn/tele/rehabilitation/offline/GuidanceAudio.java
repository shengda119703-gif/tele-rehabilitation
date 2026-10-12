package cn.tele.rehabilitation.offline;

import android.app.Activity;
import android.os.Bundle;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;
import java.util.Set;

/** Single optional, installed OFFLINE voice. Never download or defer old text. */
final class GuidanceAudio {
    interface Result { void finished(String id); }
    private final Activity activity;
    private final Result result;
    private TextToSpeech tts;
    private volatile boolean ready;
    private volatile boolean foreground = true, destroyed;
    private String currentId;
    GuidanceAudio(Activity activity, Result result) { this.activity=activity;this.result=result; }
    boolean available() { return ready&&foreground&&!destroyed; }
    void prepare() {
        if(tts!=null||destroyed||!foreground)return;
        try{tts=new TextToSpeech(activity,status->activity.runOnUiThread(()->{
            if(destroyed||tts==null||status!=TextToSpeech.SUCCESS)return;
            try {
                Set<Voice> voices=tts.getVoices();Voice chosen=null;
                if(voices!=null)for(Voice voice:voices) {
                    if(!"zh".equals(voice.getLocale().getLanguage())||voice.isNetworkConnectionRequired()||voice.getFeatures()!=null&&voice.getFeatures().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED))continue;
                    if(chosen==null||voice.getQuality()>chosen.getQuality())chosen=voice;
                }
                if(chosen==null||tts.setVoice(chosen)!=TextToSpeech.SUCCESS)return;
                tts.setSpeechRate(0.9f);
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener(){
                    @Override public void onStart(String id){}
                    @Override public void onDone(String id){finish(id);}
                    @Override public void onError(String id){finish(id);}
                    @Override public void onStop(String id,boolean interrupted){finish(id);}
                });
                ready=true; // Late initialization does NOT enqueue a saved cue.
            }catch(RuntimeException unavailable){ready=false;}
        }));}catch(RuntimeException unavailable){ready=false;}
    }
    void speak(String id,String text) {
        if(!ready||!foreground||destroyed||tts==null){result.finished(id);return;}
        currentId=id;
        try { if(tts.speak(text,TextToSpeech.QUEUE_FLUSH,new Bundle(),id)==TextToSpeech.ERROR)finish(id); }
        catch(RuntimeException unavailable){finish(id);}
    }
    private void finish(String id) { activity.runOnUiThread(()->{if(destroyed||!id.equals(currentId))return;currentId=null;result.finished(id);}); }
    void stop() { currentId=null;if(tts!=null)try{tts.stop();}catch(RuntimeException ignored){} }
    void pause() { foreground=false;stop(); }
    void resume() { if(!destroyed)foreground=true; }
    void destroy() { destroyed=true;ready=false;stop();if(tts!=null){tts.shutdown();tts=null;} }
}
