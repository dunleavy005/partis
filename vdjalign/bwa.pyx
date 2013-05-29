# distutils: language = c
# distutils: include_dirs = BWA_INCLUDE
# distutils: extra_compile_args = BWA_FLAGS
# distutils: sources = BWA_SRC
# distutils: libraries = BWA_LIBS
"""
*Very* primitive wrappers for BWA-MEM.

Currently no support for changing *any* options.
"""

import collections

from libc.stdint cimport uint64_t, uint8_t, int8_t, int64_t, uint32_t, int32_t
from libc.stdlib cimport free, malloc
from libc.string cimport memcpy

cdef extern from "bntseq.h":
    ctypedef struct bntann1_t:
        int64_t offset
        char *name
    ctypedef struct bntseq_t:
        int64_t l_pac
        int32_t n_seqs
        uint32_t seed
        bntann1_t *anns

    uint8_t *bns_get_seq(int64_t l_pac, const uint8_t *pac, int64_t beg, int64_t end, int64_t *len)

cdef extern from "bwt.h":
    ctypedef uint64_t bwtint_t

    ctypedef struct bwt_t:
        pass

cdef extern from "bwa.h":
    ctypedef struct bwaidx_t:
        bwt_t *bwt
        bntseq_t *bns
        uint8_t *pac

    bwaidx_t* bwa_idx_load(const char *hint, int which)
    void bwa_idx_destroy(bwaidx_t *idx)


cdef extern from "bwamem.h":
    ctypedef struct mem_opt_t:
        int pen_clip  # Clipping penalty
        int min_seed_len # Minimum seed length

    mem_opt_t *mem_opt_init()
    void mem_fill_scmat(int a, int b, int8_t mat[25])

    ctypedef struct mem_alnreg_t:
        pass

    ctypedef struct mem_alnreg_v:
        size_t n
        size_t m
        mem_alnreg_t *a

    ctypedef struct mem_aln_t:
        int64_t pos
        int rid # Reference id (<0 = unmapped)
        int flag
        uint32_t is_rev, mapq, NM
        int n_cigar
        uint32_t *cigar # CIGAR in the BAM encoding: opLen<<4|op; op to integer mapping: MIDSH=>01234

        int score

    mem_alnreg_v mem_align1(const mem_opt_t *opt, const bwt_t *bwt, const bntseq_t *bns, const uint8_t *pac, int l_seq, const char *seq) nogil

    mem_aln_t mem_reg2aln(const mem_opt_t *opt, const bntseq_t *bns, const uint8_t *pac, int l_seq, const char *seq, const mem_alnreg_t *ar)

cdef list parse_cigar(uint32_t *cigar, int n_cigar):
    """
    Parse a cigar array into a list of (n_ops, op) pairs.
    """
    cdef list result = []
    cdef int i, n_ops
    cdef char op
    cdef const char* ops = "MIDSH"
    for i in xrange(n_cigar):
        op = ops[cigar[i] & 0xF]
        n_ops = cigar[i] >> 4
        result.append((n_ops, chr(op)))
    return result

"""A Variation"""
Variant = collections.namedtuple('Variant', ['gene', 'type', 'ref_loc', 'query_loc', 'wt', 'mut', 'length'])

cdef class AlignedRead:
    cdef BwaIndex idx
    cdef int pos, rid, flag
    cdef bytes strand
    cdef int mapq
    cdef int nm
    cdef uint32_t* cigar
    cdef int score
    cdef int n_cigar
    cdef bytes query

    def __init__(self):
        raise ValueError("This class cannot be instantiated from Python.")

    def __dealloc__(self):
        if self.cigar != NULL:
            free(self.cigar)

    property score:
        def __get__(self):
            return self.score
    property pos:
        def __get__(self):
            return self.pos
    property rid:
        def __get__(self):
            return self.pos
    property flag:
        def __get__(self):
            return self.flag
    property mapq:
        def __get__(self):
            return self.mapq
    property n_cigar:
        def __get__(self):
            return self.n_cigar
    property query:
        def __get__(self):
            return self.query

    property reference:
        def __get__(self):
            return self.idx.idx.bns.anns[self.rid].name

    property cigar:
        def __get__(self):
            return parse_cigar(self.cigar, self.n_cigar)

    def aligned_pairs(self):
        """
        Yields pairs of (qry_idx, ref_idx) for all aligned bases.
        Soft- and hard-clipped bases are excluded.
        """
        cdef int n, i
        cdef bytes op
        cdef int qry_idx = 0
        cdef int ref_idx = self.pos

        result = []
        for n, op in parse_cigar(self.cigar, self.n_cigar):
            if op == 'S' or op == 'H':
                qry_idx += n
            else:
                for i in xrange(n):
                    if op == 'I':
                        result.append((qry_idx, None))
                        qry_idx += 1
                    elif op == 'D':
                        result.append((None, ref_idx))
                        ref_idx += 1
                    elif op == 'M':
                        result.append((qry_idx, ref_idx))
                        qry_idx += 1
                        ref_idx += 1
        return result

    def identify_variations(self):
        cdef int n, i
        cdef bytes op, ref_bases, reference = self.reference
        cdef int qry_idx = 0
        cdef int pos = self.pos
        cdef int ref_idx = 0
        cdef bytes rbase
        cdef bytes qbase

        cigar = parse_cigar(self.cigar, self.n_cigar)
        ref_length = sum(n for n, op in cigar if op in 'MD')
        assert ref_length, cigar
        ref_bases = self.idx.fetch_reference(self.rid, self.pos, self.pos + ref_length)
        assert len(ref_bases) == ref_length

        for n, op in parse_cigar(self.cigar, self.n_cigar):
            if op in 'HS': # Clipped
                qry_idx += n
            elif op == 'I':
                yield Variant(reference, op, pos + ref_idx, qry_idx, None, self.query[qry_idx:qry_idx + n], n)
                qry_idx += n
            else:
                for i in xrange(n):
                    if op == 'M':
                        if ref_idx - pos >= len(ref_bases):
                            print ref_idx, pos, len(ref_bases)
                        rbase = ref_bases[ref_idx]
                        qbase = self.query[qry_idx]
                        if rbase != qbase:
                            yield Variant(self.reference, op, pos + ref_idx, qry_idx, rbase, qbase, 1)
                        ref_idx += 1
                        qry_idx += 1
                    elif op == 'D':
                        yield Variant(self.reference, op, pos + ref_idx, qry_idx, ref_bases[ref_idx], None, 1)
                        ref_idx += 1
                    else:
                        raise ValueError(op)

cdef class BwaIndex:
    """
    A loaded BWA index
    """
    cdef bwaidx_t *idx
    cdef mem_opt_t *opt
    cdef bytes path
    def __init__(self):
        raise ValueError("This class cannot be instantiated from Python.")

    def __dealloc__(self):
        if self.idx != NULL:
            bwa_idx_destroy(self.idx)
        if self.opt != NULL:
            free(self.opt)

    def __repr__(self):
        return '<BwaIndex {0}>'.format(self.path)

    property pen_clip:
        def __get__(self):
            return self.opt.pen_clip
        def __set__(self, int value):
            self.opt.pen_clip = value

    property min_seed_len:
        def __get__(self):
            return self.opt.min_seed_len
        def __set__(self, int value):
            self.opt.min_seed_len = value

    def align(self, bytes seq):
        """
        Align a sequence
        """
        cdef char* s = seq
        cdef int l_seq = len(seq)
        cdef uint32_t i

        cdef int BWA_IDX_ALL = 0x7

        cdef mem_alnreg_v ar
        cdef mem_aln_t a
        cdef AlignedRead read
        try:
            with nogil:
                ar = mem_align1(self.opt, self.idx.bwt, self.idx.bns, self.idx.pac, l_seq, s)
            result = []
            for i in xrange(ar.n):
                a = mem_reg2aln(self.opt, self.idx.bns, self.idx.pac, l_seq, s, &ar.a[i])
                read = AlignedRead.__new__(AlignedRead)
                read.idx = self
                read.pos = a.pos
                read.rid = a.rid
                read.flag = a.flag
                read.mapq = a.mapq
                read.strand = "+-"[a.is_rev]
                read.nm = a.NM
                read.query = seq
                read.cigar = <uint32_t*>malloc(sizeof(uint32_t) * a.n_cigar)
                memcpy(<void*>read.cigar, a.cigar, sizeof(uint32_t) * a.n_cigar)
                read.n_cigar = a.n_cigar
                read.score = a.score

                result.append(read)
                free(a.cigar)
            return result
        finally:
            free(ar.a)

    def fetch_reference(self, int rid, int rbegin, int rend):
        """
        Fetch bases from reference ``rid``, from ``rbegin`` to ``rend``
        """
        cdef int64_t offset = self.idx.bns.anns[rid].offset
        cdef list l
        cdef uint8_t *result
        cdef int64_t length
        cdef int i, c_idx
        cdef char c
        cdef const char *bases = "ACGT"
        try:
            result = bns_get_seq(self.idx.bns.l_pac, self.idx.pac, rbegin + offset, rend + offset, &length)
            l = [None for i in xrange(length)]
            for i in xrange(length):
                c_idx = result[i]
                c = bases[c_idx]
                l[i] = chr(c)
            return ''.join(l)
        finally:
            free(result)

def load_index(bytes index_path, int min_seed_len=15, int pen_clip=0):
    cdef int BWA_IDX_ALL = 0x7
    cdef bwaidx_t *idx = bwa_idx_load(index_path, BWA_IDX_ALL)
    if idx == NULL:
        raise IOError("Could not open " + index_path)

    cdef BwaIndex result = BwaIndex.__new__(BwaIndex)

    result.idx = idx
    result.path = index_path
    result.opt = mem_opt_init()
    result.opt.pen_clip = pen_clip
    result.opt.min_seed_len = min_seed_len

    return result
