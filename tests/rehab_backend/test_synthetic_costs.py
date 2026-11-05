"""Pure file/time cost audit checks; no server, models, network or GPU."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from tools.rehab_ml.synthetic.costs import (build_report, classify_job, job_timing,
    observed_resources, parse_gpu_timestamp, read_gpu_samples, read_memory_samples, write_report)


def job(start=100., end=110.):
    return dict(name='TEST',prompt_id='TEST-id',created_unix=start-5.,finished_unix=end+9.,status='success',
        workflow={'1':{'class_type':'EmptyLTXVLatentVideo','inputs':{'length':97}},
                  '2':{'class_type':'LabSaveMP4','inputs':{}}},
        history={'status':{'messages':[
            ['execution_start',{'prompt_id':'TEST-id','timestamp':start*1000}],
            ['execution_success',{'prompt_id':'TEST-id','timestamp':end*1000}]]}})


class SyntheticCostsTests(unittest.TestCase):
    def test_local_csv_unix_memory_and_comfy_ms_share_same_execution_window(self):
        start=parse_gpu_timestamp('2026/10/19 01:00:00.000')
        self.assertEqual(start,datetime(2026,10,18,17,tzinfo=timezone.utc).timestamp())
        timing=job_timing(job(start,start+10.))
        self.assertEqual(timing['observer_wall_seconds'],24.)
        self.assertEqual(timing['execution_wall_seconds'],10.)
        self.assertTrue(timing['execution_window_verified'])
        with tempfile.TemporaryDirectory(prefix='synthetic-costs-TEST-') as temporary:
            root=Path(temporary)
            gpu=root/'gpu.csv'
            gpu.write_text('timestamp, memory.used [MiB], utilization.gpu [%], temperature.gpu, power.draw [W]\n'
                '2026/10/19 00:59:59.000, 9999 MiB, 100 %, 99, 999 W\n'
                '2026/10/19 01:00:00.000, 4000 MiB, 70 %, 78, 65.5 W\n'
                '2026/10/19 01:00:10.000, 5000 MiB, 90 %, 80, 66 W\n'
                '2026/10/19 01:00:11.000, 9999 MiB, 100 %, 99, 999 W\n',encoding='utf-8')
            memory=root/'memory.jsonl'
            memory.write_text('\n'.join(json.dumps(dict(unix_time=t,server_rss_gib=r,
                available_physical_gib=f,available_commit_gib=f+2)) for t,r,f in
                [(start-1,30,.1),(start+1,12,5),(start+9,14,4),(start+11,30,.1)])+'\n',encoding='utf-8')
            resources=observed_resources(timing,read_gpu_samples(gpu)[0],read_memory_samples(memory)[0])
            self.assertEqual(resources['max_observed_gpu_memory_mib'],dict(value=5000.,samples=2))
            self.assertEqual(resources['max_observed_server_rss_gib'],dict(value=14,samples=2))
            self.assertEqual(resources['min_observed_available_physical_gib'],dict(value=4,samples=2))
            self.assertEqual(resources['gpu_window_samples']['max_observed_sampling_gap_s'],10.)

    def test_missing_samples_and_unfinished_or_ambiguous_events_never_infer_peak(self):
        data=job()
        data['history']['status']['messages'].pop()
        timing=job_timing(data)
        self.assertIsNone(timing['execution_wall_seconds'])
        resources=observed_resources(timing,[{'unix_time':105.,'gpu_memory_mib':6000.}],[])
        self.assertEqual(resources['max_observed_gpu_memory_mib'],dict(value=None,samples=0))
        data=job()
        data['history']['status']['messages'].append(['execution_start',{'prompt_id':'TEST-id','timestamp':101000}])
        self.assertFalse(job_timing(data)['execution_window_verified'])
        data=job()
        data['history']['status']['messages'][1][1]['prompt_id']='another-job'
        self.assertEqual(job_timing(data)['ignored_execution_events'],1)
        self.assertFalse(job_timing(data)['execution_window_verified'])

    def test_categories_are_workflow_buckets_not_filenames_or_motion_labels(self):
        data=job()
        data['name']='not-a-reference'
        self.assertEqual(classify_job(data),('reference_97',97))
        data['workflow']['1']['inputs']['length']=241
        self.assertEqual(classify_job(data),('action_241',241))
        data['workflow']={'1':{'class_type':'CLIPTextEncode'},'2':{'class_type':'LabSaveConditioning'}}
        self.assertEqual(classify_job(data),('text_conditioning',None))

    def test_invalid_monitor_rows_are_counted_and_missing_values_stay_unknown(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-costs-TEST-') as temporary:
            root=Path(temporary)
            memory=root/'memory.jsonl'
            memory.write_text('{"unix_time":100,"server_rss_gib":null}\n{"unix_time":\n',encoding='utf-8')
            rows,source=read_memory_samples(memory)
            self.assertEqual(len(rows),1)
            self.assertEqual(source['rejected_rows'],[2])
            self.assertIsNone(rows[0]['server_rss_gib'])
            missing=read_gpu_samples(root/'missing.csv')
            self.assertEqual(missing[0],[])
            self.assertFalse(missing[1]['exists'])

    def test_report_only_reads_inputs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-costs-TEST-') as temporary:
            root=Path(temporary)
            directory=root/'manifests/jobs'
            directory.mkdir(parents=True)
            source=directory/'job.json'
            original=json.dumps(job())
            source.write_text(original,encoding='utf-8')
            report=build_report(root,lab=root)
            self.assertEqual(report['job_count'],1)
            self.assertFalse(report['interpretation']['sampled_extrema_are_continuous_peaks'])
            self.assertIsNone(report['jobs'][0]['stage_seconds']['sampling'])
            self.assertEqual(report['jobs'][0]['resources']['gpu_window_samples']['samples'],0)
            path=write_report(report,root/'new-report.json')
            with self.assertRaises(FileExistsError):
                write_report(report,path)
            self.assertEqual(source.read_text(encoding='utf-8'),original)


if __name__=='__main__':
    unittest.main()
