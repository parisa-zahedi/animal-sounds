import pandas as pd
import librosa
import soundfile as sf
import os
import argparse


def parse_arguments():
    # parse arguments if available
    parser = argparse.ArgumentParser(
        description="Process Raven files"
    )
    # File path to the data.
    parser.add_argument(
        "raven_file",
        type=str,
        help="File path to the annotation dataset"
    )
    # Annotation class
    parser.add_argument(
        "species",
        type=str,
        help="Only process annotation of this class"
    )
    # Raw files location
    parser.add_argument(
        "wavpath",
        type=str,
        help="Location of raw wav files"
    )
    parser.add_argument(
        "outputdir",
        type=str,
        help="Output directory"
    )
    parser.add_argument(
        "recID",
        type=str,
        help="Recorder Identifier"
    )
    parser.add_argument(
        "min_sig_len",
        type=float,
        help="Minimal Signal Length (s)"
    )
    parser.add_argument(
        "bg_padding_len",
        type=float,
        help="Standard Background Padding Length (s)"
    )

    parser.add_argument(
        "startindex",
        type=int,
        default=0,
        help="Start index for numbering output files"
    )
    parser.add_argument(
        '-c', '--createframes',
        action='store_true',
        dest='createframes',
        help='Cut annotations into multiple frames'
    )

    return parser


class ProcessRaven:
    def __init__(self, file, wav_path):
        self.filelist = sorted(os.listdir(wav_path))
        self.df = None
        self.df_2 = None
        self.df_pad = None
        self.duration = None
        self.file = file
        self.file_lengths = None
        self.wav_path = wav_path

    def raven_input(self):
        self.df = pd.read_table(self.file)
        self.df.columns = self.df.columns.str.lower()
        print(self.df.columns)

    def wav_file_len(self, wav_path):
        len_file_list = []
        for f in self.filelist:
            len_file = librosa.get_duration(filename=wav_path + f)
            len_file_list.append(len_file)

        df = pd.DataFrame(columns=['file', 'filelength'])
        df['file'], df['filelength'] = self.filelist, len_file_list
        self.file_lengths = df

    @staticmethod
    def fix_multifile(df_out, filelist, wav_path):
        row_i = list(df_out[(df_out['begin_path']
                             != df_out['end_path'])].index)

        for i in row_i:
            df = pd.DataFrame([[df_out.loc[i, 'begin_path'],
                                df_out.loc[i, 'begin_path'],
                                df_out.loc[i, 'start_time'],
                                df_out.loc[i, 'filelength'],
                                df_out.loc[i, 'filelength']],
                               [df_out.loc[i, 'end_path'],
                                df_out.loc[i, 'end_path'],
                                0.0,
                                df_out.loc[i, 'end_time']
                                - df_out.loc[i, 'filelength'],
                                df_out.loc[i, 'filelength']]],
                              columns=['begin_path',
                                       'end_path',
                                       'start_time',
                                       'end_time',
                                       'filelength'])

            df_out = df_out.append(df, ignore_index=True)

            if (filelist.index(df_out.loc[i, 'end_path'])
                    - filelist.index(df_out.loc[i, 'begin_path'])) > 1:
                for j in range(filelist.index(df_out.loc[i, 'begin_path'])
                               + 1, filelist.index(df_out.loc[i, 'end_path'])):
                    print(j)
                    len_file = librosa.get_duration(
                        filename=wav_path + filelist[j])
                    df = pd.DataFrame([[filelist[j],
                                        filelist[j],
                                        0.0,
                                        len_file,
                                        len_file]],
                                      columns=['begin_path',
                                               'end_path',
                                               'start_time',
                                               'end_time',
                                               'filelength'])
                df_out = df_out.append(df, ignore_index=True)
        return df_out.drop(row_i)

    def process_raven(self, species, min_sig_len):
        df = self.df.rename(columns={'begin path': 'begin_path',
                                     'end path': 'end_path'})

        # select only relevant colums
        if 'class' in df.columns:
            df = df.rename(columns={"class": "species"})

        df_3 = df.loc[(df['species'] == species)
                      & ((df['end time (s)'] - df['begin time (s)'])
                         > min_sig_len),
                      ['begin_path',
                       'end_path',
                       'begin time (s)',
                       'end time (s)',
                       'file offset (s)',
                       'type']]

        # Cut first part of string
        df_3['begin_path'] = df_3['begin_path'].str.replace('.*\\\\',
                                                            '', regex=True)
        df_3['end_path'] = df_3['end_path'].str.replace('.*\\\\',
                                                        '', regex=True)

        df_3 = pd.merge(df_3, self.file_lengths,
                        left_on='begin_path', right_on='file')

        # Change timestamps to timestamps relative to file
        df_3['start_time'] = df_3['file offset (s)']
        df_3['end_time'] = (df_3['file offset (s)']
                            + df_3['end time (s)'] - df_3['begin time (s)'])

        df_3 = self.fix_multifile(df_3, self.filelist, self.wav_path)

        # Select columns of interest
        df_4 = df_3.loc[:, ['begin_path',
                            'end_path',
                            'start_time',
                            'end_time',
                            'type',
                            'filelength']]
        df_4 = df_4.reset_index()
        self.df_2 = df_4.drop(columns=['index'])
        self.df_2 = self.df_2.drop(
            self.df_2[self.df_2['end_time']
                      - self.df_2['start_time'] < 0.2].index)
        self.duration = self.df_2['end_time'] - self.df_2['start_time']

    def padding(self, df, wav_path, min_bg_padding, min_length):
        self.df_pad = pd.DataFrame({'file': [], 'start': [], 'duration': []})
        for index, row in df.iterrows():
            file = wav_path + row.begin_path
            duration = max(min_length, min(
                row.end_time - row.start_time + 2 * min_bg_padding, 60.0))
            if duration < row.filelength - 2 * min_bg_padding:
                bg_padding = max(min_bg_padding,
                                 (min_length - (row.end_time - row.start_time))
                                 / 2)
                start = (max(row.start_time - bg_padding, 0.0)
                         - max(0.0,
                               (row.end_time + bg_padding) - row.filelength))
            else:
                start = 0.0
                duration = 60.0
            print(duration)
            self.df_pad = self.df_pad.append({'file': file,
                                              'start': start,
                                              'duration': duration},
                                             ignore_index=True)
        self.df_pad['type'] = list(df['type'])
        self.df_pad['filename'] = list(df['begin_path'])


def write_files(df, output_path, species, rec_id, createframes,
                k_start, frame_len, jump_len):
    k = k_start
    kk = 0  # second fileindex for output files (when n raven files > 1)
    df2 = pd.DataFrame(columns=['id', 'recorder_id',
                                'file', 'start', 'duration', 'type', 'wav'])

    for index in range(len(df)):
        file = df['file'].iloc[index]
        filename = df['filename'].iloc[index]
        print(index, file[0:-4])
        y, sr = librosa.load(file, sr=48000,
                             offset=df['start'].iloc[index],
                             duration=df['duration'].iloc[index])

        if createframes and df['duration'].iloc[index] >= frame_len + jump_len:
            frames = librosa.util.frame(y, frame_length=frame_len * sr,
                                        hop_length=jump_len * sr, axis=0)
            nframes = len(frames)
            # nframes = int(np.floor(df['duration'].iloc[index] - jump_len))
            print(nframes)
            for i in range(nframes):
                outfile1 = (str(k) + '_' + str(index) + '_'
                            + filename[0:-4] + '_'
                            + str(round(df['start'].iloc[index] + i, 6))
                            + '.wav')
                out_file = output_path + outfile1
                sf.write(out_file, frames[i], sr)

                df2.at[kk, 'id'] = k
                df2.iloc[kk, 1:6] = [rec_id,
                                     filename,
                                     str(round(
                                         df['start'].iloc[index] + i, 6)),
                                     frame_len,
                                     df['type'].iloc[index]]
                df2.at[kk, 'wav'] = outfile1
                k = k + 1
                kk = kk + 1

        else:
            outfile1 = (str(k) + '_' + rec_id + '_' + filename[0:-4] + '_'
                        + str(round(df['start'].iloc[index], 6)) + '.wav')
            out_file = output_path + outfile1
            sf.write(out_file, y, sr)
            df2.at[kk, 'id'] = k
            df2.iloc[kk, 1:6] = [rec_id,
                                 filename,
                                 str(round(df['start'].iloc[index], 6)),
                                 df['duration'].iloc[index],
                                 df['type'].iloc[index]]
            df2.at[kk, 'wav'] = outfile1
            k = k + 1
            kk = kk + 1

    if k_start == 0:
        df2.to_csv(output_path + species.lower() + '.csv')
    else:
        df2.to_csv(output_path + species.lower()
                   + '.csv', mode='a', header=False)


def main():
    parser = parse_arguments()
    args = parser.parse_args()

    p1 = ProcessRaven(args.raven_file, args.wavpath)
    p1.raven_input()
    p1.wav_file_len(args.wavpath)
    p1.process_raven(args.species, args.min_sig_len)
    p1.padding(p1.df_2, args.wavpath, args.bg_padding_len, min_length=0.5)
    write_files(p1.df_pad, args.outputdir, args.species, args.recID,
                args.createframes, args.startindex, frame_len=2, jump_len=1)


if __name__ == '__main__':
    main()
