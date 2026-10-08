//! Cache view indexes between renders. Records stay owned by the snapshot.
use crate::query::SortOrder;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Key {
    pub revision: u64,
    pub source: (usize, usize),
    pub query: String,
    pub sort: SortOrder,
    pub at: u64,
}

#[derive(Default)]
pub struct Rows {
    entries: [Option<(Key, Vec<usize>)>; 3],
    pub builds: u64,
}

impl Rows {
    pub fn get(&mut self, view: usize, key: Key, build: impl FnOnce() -> Vec<usize>) -> Vec<usize> {
        if self.entries[view]
            .as_ref()
            .is_none_or(|(previous, _)| previous != &key)
        {
            self.entries[view] = Some((key, build()));
            self.builds += 1;
        }
        self.entries[view].as_ref().unwrap().1.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn repeated_draws_reuse_indexes_and_query_or_snapshot_invalidates_them() {
        let mut cache = Rows::default();
        let mut key = Key {
            revision: 1,
            source: (1, 10),
            query: "termine".into(),
            sort: SortOrder::Date,
            at: 1000,
        };
        assert_eq!(cache.get(0, key.clone(), || vec![7]), vec![7]);
        assert_eq!(
            cache.get(0, key.clone(), || panic!("unnecessary rebuild")),
            vec![7]
        );
        key.query = "mpi".into();
        assert_eq!(cache.get(0, key.clone(), || vec![2]), vec![2]);
        key.revision += 1;
        cache.get(0, key, Vec::new);
        assert_eq!(cache.builds, 3);
    }
}
