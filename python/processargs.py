import os
import random
import sys
import subprocess

import utils

# ----------------------------------------------------------------------------------------
def process(args):
    if args.action == 'run-viterbi':
        print'  note: replacing deprecated action name \'run-viterbi\' with current name \'annotate\' (this doesn\'t change any actual behavior)'
        args.action = 'annotate'

    if args.chain is not None:
        print '    note: transferring argument from deprecated option \'--chain %s\' to new option \'--locus %s\'' % (args.chain, 'ig' + args.chain)
        args.locus = 'ig' + args.chain
        args.chain = None
    args.loci = utils.get_arg_list(args.loci, choices=utils.loci)
    if args.loci is None:  # in principle I should check that at least one of 'em isn't None, but if that's the case it'll crash soon enough
        args.loci = [args.locus]
    else:
        args.locus = args.loci[0]

    args.only_genes = utils.get_arg_list(args.only_genes)
    args.queries = utils.get_arg_list(args.queries)
    args.queries_to_include = utils.get_arg_list(args.queries_to_include)
    args.reco_ids = utils.get_arg_list(args.reco_ids)
    args.istartstop = utils.get_arg_list(args.istartstop, intify=True)
    if args.istartstop is not None:
        if args.istartstop[0] >= args.istartstop[1] or args.istartstop[0] < 0:
            raise Exception('invalid --istartstop specification: %d %d' % (args.istartstop[0], args.istartstop[1]))
    args.n_max_per_region = utils.get_arg_list(args.n_max_per_region, intify=True)
    if len(args.n_max_per_region) != 3:
        raise Exception('n-max-per-region should be of the form \'x:y:z\', but I got ' + str(args.n_max_per_region))
    args.write_additional_cluster_annotations = utils.get_arg_list(args.write_additional_cluster_annotations, intify=True)
    if args.write_additional_cluster_annotations is not None and len(args.write_additional_cluster_annotations) != 2:
        raise Exception('--write-additional-cluster-annotations must be specified as two numbers \'m:n\', but I got %s' % args.write_additional_cluster_annotations)
    args.extra_annotation_columns = utils.get_arg_list(args.extra_annotation_columns, choices=utils.extra_annotation_headers)

    args.cluster_indices = utils.get_arg_list(args.cluster_indices, intify=True)

    args.region_end_exclusions = {r : [args.region_end_exclusion_length if ('%s_%s' % (r, e)) in utils.real_erosions else 0 for e in ['5p', '3p']] for r in utils.regions}
    args.region_end_exclusion_length = None  # there isn't really a big reason to set it to None, but this makes clear that I should only be using the dict version

    args.annotation_clustering_thresholds = utils.get_arg_list(args.annotation_clustering_thresholds, floatify=True)
    args.naive_hamming_bounds = utils.get_arg_list(args.naive_hamming_bounds, floatify=True)
    if args.small_clusters_to_ignore is not None:
        if '-' in args.small_clusters_to_ignore:
            lo, hi = [int(cluster_size) for cluster_size in args.small_clusters_to_ignore.split('-')]
            args.small_clusters_to_ignore = range(lo, hi + 1)
        else:
            args.small_clusters_to_ignore = utils.get_arg_list(args.small_clusters_to_ignore, intify=True)
    if args.seed_unique_id is not None:
        args.seed_unique_id = args.seed_unique_id.strip()  # protect against the space you may put in front of it if it's got an initial minus sign (better way is to use an equals sign)
        if args.queries is not None and args.seed_unique_id not in args.queries:
            raise Exception('seed uid %s not in --queries %s' % (args.seed_unique_id, ' '.join(args.queries)))
        if args.random_seed_seq:
            raise Exception('can\'t specify both --seed-unique-id and --random-seed-seq')

        if args.queries_to_include is None:  # make sure the seed is in --queries-to-include
            args.queries_to_include = [args.seed_unique_id]
        elif args.seed_unique_id not in args.queries_to_include:
            args.queries_to_include = [args.seed_unique_id] + args.queries_to_include  # may as well put it first, I guess (?)

    if args.sw_debug is None:  # if not explicitly set, set equal to regular debug
        args.sw_debug = args.debug

    if args.only_genes is not None:
        for gene in args.only_genes:  # make sure they're all at least valid ig genes
            utils.split_gene(gene)

    if args.print_git_commit or args.action == 'version':
        print 'RUN ' + ' '.join(sys.argv)
        tag = subprocess.check_output(['git', 'tag']).split()[-1]
        print '       tag %s' % tag
        print '    commit %s' % subprocess.check_output(['git', 'rev-parse', 'HEAD']).strip()
        if args.action == 'version':
            sys.exit(0)

    args.is_data = not args.is_simu  # whole code base uses is_data, this is better than changing all of that

    if args.simultaneous_true_clonal_seqs:
        if args.is_data:
            raise Exception('can only pass true clonal families to multi-hmm together on simulation and with --is-simu set')
        if args.n_simultaneous_seqs is not None:
            raise Exception('can\'t specify both --n-simultaneous-seqs and --simultaneous-true-clonal-seqs')

    if args.no_indels:
        print 'forcing --gap-open-penalty to %d to prevent indels, since --no-indels was specified (you can also adjust this penalty directly)' % args.no_indel_gap_open_penalty
        args.gap_open_penalty = args.no_indel_gap_open_penalty

    if args.indel_frequency > 0.:
        if args.indel_frequency < 0. or args.indel_frequency > 1.:
            raise Exception('--indel-frequency must be in [0., 1.] (got %f)' % args.indel_frequency)
    args.n_indels_per_indeld_seq = utils.get_arg_list(args.n_indels_per_indeld_seq, intify=True)

    if 'tr' in args.locus and args.mutation_multiplier is None:
        args.mutation_multiplier = 0.

    if args.workdir is None:  # set default here so we know whether it was set by hand or not
        def choose_random_subdir(dirname):
            subname = str(random.randint(0, 999999))
            while os.path.exists(dirname + '/' + subname):
                subname = str(random.randint(0, 999999))
            return dirname + '/' + subname
        if args.batch_system is not None and os.path.exists('/fh/fast/matsen_e'):
            args.workdir = choose_random_subdir('/fh/fast/matsen_e/' + os.path.basename(os.getenv('HOME')) + '/_tmp/hmms')
        else:
            args.workdir = choose_random_subdir('/tmp/' + os.path.basename(os.getenv('HOME')) + '/hmms')
            if args.batch_system is not None:
                print '  %s: using batch system %s with default --workdir (%s) -- if this isn\'t visible to the batch nodes on your system, you\'ll need to change it' % (utils.color('red', 'warning'), args.batch_system, args.workdir)
    else:
        args.workdir = args.workdir.rstrip('/')
    if os.path.exists(args.workdir):
        raise Exception('workdir %s already exists' % args.workdir)

    if args.batch_system == 'sge' and args.batch_options is not None:
        if '-e' in args.batch_options or '-o' in args.batch_options:
            print '%s --batch-options contains \'-e\' or \'-o\', but we add these automatically since we need to be able to parse each job\'s stdout and stderr. You can control the directory under which they\'re written with --workdir (which is currently %s).' % (utils.color('red', 'warning'), args.workdir)

    if args.outfname is not None and not args.presto_output:
        if utils.getsuffix(args.outfname) not in ['.csv', '.yaml']:
            raise Exception('unhandled --outfname suffix %s' % utils.getsuffix(args.outfname))
        if utils.getsuffix(args.outfname) != '.yaml':
            print '  %s --outfname uses deprecated file format %s. This will still work fine, but the new default .yaml format is much cleaner, and includes annotations, partitions, and germline info in the same file.' % (utils.color('yellow', 'note:'), utils.getsuffix(args.outfname))
        if args.action in ['view-annotations', 'view-partitions'] and utils.getsuffix(args.outfname) == '.yaml':
            raise Exception('have to use \'view-output\' action to view .yaml output files')
        if args.action in ['view-output'] and utils.getsuffix(args.outfname) == '.csv':
            raise Exception('have to use \'view-annotations\' or \'view-partitions\' to view .csv output files')

    if args.presto_output:
        if args.action == 'annotate' and utils.getsuffix(args.outfname) != '.tsv':
            raise Exception('--outfname suffix has to be .tsv for annotation with --presto-output (got %s)' % utils.getsuffix(args.outfname))
        if args.action == 'partition' and utils.getsuffix(args.outfname) not in ['.fa', 'fasta']:
            raise Exception('--outfname suffix has to be .fa or .fasta for partition with --presto-output (got %s)' % utils.getsuffix(args.outfname))
        if args.aligned_germline_fname is None:
            raise Exception('in order to get presto output, you have to set --aligned-germline-fname to a fasta file with germline alignments for every germline gene, an example is located in data/germlines/imgt-aligned-igh.fa (this isn\'t set by default because imgt alignments are subject to change)')

    if args.cluster_annotation_fname is None and args.outfname is not None and utils.getsuffix(args.outfname) == '.csv':  # if it wasn't set on the command line (<outfname> _was_ set), _and_ if we were asked for a csv, then use the old file name format
        args.cluster_annotation_fname = utils.insert_before_suffix('-cluster-annotations', args.outfname)

    if args.calculate_alternative_naive_seqs or (args.action == 'view-alternative-naive-seqs' and args.persistent_cachefname is None):
        if args.outfname is None:
            raise Exception('have to specify --outfname in order to calculate alternative naive sequences')
        args.persistent_cachefname = utils.insert_before_suffix('-hmm-cache', args.outfname)
        if args.calculate_alternative_naive_seqs and os.path.exists(args.persistent_cachefname):
            if os.stat(args.persistent_cachefname).st_size == 0:
                print '  note: removing existing zero-length persistent cache file %s' % args.persistent_cachefname
                os.remove(args.persistent_cachefname)
            else:
                raise Exception('persistent cache file %s already exists, but we were asked to --calculate-alternative-naive-seqs. Either it\'s an old file (in which case you should delete it), or you\'ve already got the alternative annotations (so you can just run view-alternative-naive-seqs)' % args.persistent_cachefname)

    if args.plot_performance:
        print '%s encountered deprecated argument --plot-performance, moving value to --plot-annotation-performance' % utils.color('yellow', 'warning')
        args.plot_annotation_performance = True
    if args.plot_annotation_performance:
        if args.plotdir is None:
            raise Exception('can\'t plot performance unless --plotdir is specified')
        if not args.is_simu:
            raise Exception('can\'t plot performance unless --is-simu is set')
    if args.action == 'plot-partitions' and args.plotdir is None:
        raise Exception('--plotdir must be specified ')

    if args.parameter_type != 'hmm':
        print '  using non-default parameter type \'%s\'' % args.parameter_type

    if args.simulate_from_scratch:
        args.rearrange_from_scratch = True
        args.mutate_from_scratch = True
    if args.flat_mute_freq or args.same_mute_freq_for_all_seqs:
        assert args.mutate_from_scratch

    if args.action == 'simulate':
        if len(args.loci) != 1:
            raise Exception('needs to be implemented')
        if args.batch_system is not None and args.n_procs > 1 and not args.subsimproc:
            print '  %s setting subsimproc' % utils.color('red', 'warning')
            args.subsimproc = True
        if args.n_trees is None:
            args.n_trees = max(1, int(float(args.n_sim_events) / args.n_procs))
        if args.outfname is None:
            print '  note: no --outfname specified, so nothing will be written to disk'
        if args.n_max_queries != -1:
            print '  note: --n-max-queries is not used when simulating (use --n-sim-events to set the simulated number of rearrangemt events)'

        # end result of this block: shm/reco parameter dirs are set (unless we're doing their bit from scratch), --parameter-dir is set to None (and if --parameter-dir was set but shm/reco were _not_ set, we've just used --parameter-dir for either/both as needed)
        if args.parameter_dir is not None:
            if args.rearrange_from_scratch or args.mutate_from_scratch:
                raise Exception('can\'t set --parameter-dir if rearranging or mutating from scratch (use --reco-parameter-dir and/or --shm-parameter-dir)')
            if args.reco_parameter_dir is not None or args.shm_parameter_dir is not None:
                raise Exception('can\'t set --parameter-dir if either --reco-parameter-dir or --shm-parameter-dir are also set')
            args.reco_parameter_dir = args.parameter_dir
            args.shm_parameter_dir = args.parameter_dir
            args.parameter_dir = None
        if args.rearrange_from_scratch and args.reco_parameter_dir is not None:
            raise Exception('doesn\'t make sense to set both --rearrange-from-scratch and --reco-parameter-dir')
        if args.mutate_from_scratch and args.shm_parameter_dir is not None:
            raise Exception('doesn\'t make sense to set both --mutate-from-scratch and --shm-parameter-dir')
        if args.reco_parameter_dir is None and not args.rearrange_from_scratch:
            raise Exception('have to either set --rearrange-from-scratch or --reco-parameter-dir')
        if args.shm_parameter_dir is None and not args.mutate_from_scratch:
            raise Exception('have to either set --mutate-from-scratch or --shm-parameter-dir')

        if args.generate_germline_set and not args.rearrange_from_scratch:
            raise Exception('can only --generate-germline-set if also rearranging from scratch (set --rearrange-from-scratch)')

    if args.parameter_dir is not None:
        args.parameter_dir = args.parameter_dir.rstrip('/')

    if args.count_parameters and not args.dont_write_parameters:
        raise Exception('if you set --count-parameters, you should also set --dont-write-parameters to make sure you\'re not accidentally overwriting existing parameters ')

    if os.path.exists(args.default_initial_germline_dir + '/' + args.species):  # ick that is hackey
        args.default_initial_germline_dir += '/' + args.species

    if args.species != 'human' and not args.allele_cluster:
        print '  non-human species \'%s\', turning on allele clustering' % args.species
        args.allele_cluster = True

    if args.n_max_snps is not None and args.n_max_mutations_per_segment is not None:
        if args.n_max_snps > args.n_max_mutations_per_segment - 10:
            raise Exception('--n-max-snps should be at least ten less than --n-max-mutations-per-segment, but I got %d and %d' % (args.n_max_snps, args.n_max_mutations_per_segment))

    if args.n_alleles_per_gene is None:
        if not args.dont_find_new_alleles:
            args.n_alleles_per_gene = 1
        else:
            args.n_alleles_per_gene = 2

    if args.leave_default_germline:
        args.dont_remove_unlikely_alleles = True
        args.allele_cluster = False
        args.dont_find_new_alleles = True

    if args.infname is None and args.action not in ['simulate', 'view-output', 'view-annotations', 'view-partitions', 'view-cluster-annotations', 'plot-partitions', 'view-alternative-naive-seqs']:
        raise Exception('--infname is required for action \'%s\'' % args.action)
