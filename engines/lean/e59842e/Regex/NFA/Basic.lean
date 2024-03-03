namespace NFA

inductive Node where
  | done
  | fail
  | epsilon (next : Nat)
  | char (c : Char) (next : Nat)
  | split (next₁ next₂ : Nat)
  | save (offset : Nat) (next : Nat)
deriving Repr

def Node.inBounds (node : Node) (size : Nat) : Bool :=
  match node with
  | Node.done => true
  | Node.fail => true
  | Node.epsilon next => next < size
  | Node.char _ next => next < size
  | Node.split next₁ next₂ => next₁ < size && next₂ < size
  | Node.save _ next => next < size

def Node.InboundsType (n : Node) (size : Nat) : Prop :=
  match n with
  | .done => True
  | .fail => True
  | .epsilon next => next < size
  | .char _ next => next < size
  | .split next₁ next₂ => next₁ < size ∧ next₂ < size
  | .save _ next => next < size

theorem Node.inBounds_iff (node : Node) (size : Nat) :
  node.inBounds size ↔ Node.InboundsType node size := by
  cases node <;> simp [Node.InboundsType, Node.inBounds]

@[simp]
theorem Node.inBounds.done {size : Nat} : Node.done.inBounds size := by
  simp [inBounds]

@[simp]
theorem Node.inBounds.fail {size : Nat} : Node.fail.inBounds size := by
  simp [inBounds]

@[simp]
theorem Node.inBounds.epsilon {size next : Nat} (h : next < size) :
  (Node.epsilon next).inBounds size := by
  simp [inBounds, h]

@[simp]
theorem Node.inBounds.char {size next : Nat} {c : Char} (h : next < size) :
  (Node.char c next).inBounds size := by
  simp [inBounds, h]

@[simp]
theorem Node.inBounds.split {size next₁ next₂ : Nat} (h₁ : next₁ < size) (h₂ : next₂ < size) :
  (Node.split next₁ next₂).inBounds size := by
  simp [inBounds, h₁, h₂]

@[simp]
theorem Node.inBounds.save {size offset next : Nat} (h : next < size) :
  (Node.save offset next).inBounds size := by
  simp [inBounds, h]

theorem Node.lt_of_inBounds.epsilon {size next : Nat} (h : (Node.epsilon next).inBounds size) :
  next < size := by
  simp [inBounds] at h
  exact h

theorem Node.lt_of_inBounds.char {size next : Nat} {c : Char} (h : (Node.char c next).inBounds size) :
  next < size := by
  simp [inBounds] at h
  exact h

theorem Node.lt_of_inBounds.split {size next₁ next₂ : Nat} (h : (Node.split next₁ next₂).inBounds size) :
  next₁ < size ∧ next₂ < size := by
  simp [inBounds] at h
  exact h

theorem Node.lt_of_inBounds.split_left {size next₁ next₂ : Nat} (h : (Node.split next₁ next₂).inBounds size) :
  next₁ < size := (Node.lt_of_inBounds.split h).left

theorem Node.lt_of_inBounds.split_right {size next₁ next₂ : Nat} (h : (Node.split next₁ next₂).inBounds size) :
  next₂ < size := (Node.lt_of_inBounds.split h).right

theorem Node.lt_of_inBounds.save {size offset next : Nat} (h : (Node.save offset next).inBounds size) :
  next < size := by
  simp [inBounds] at h
  exact h

theorem Node.inBounds_of_inBounds_of_le {n : Node} (h : n.inBounds size) (le : size ≤ size') :
  n.inBounds size' := by
  simp [inBounds] at *
  split <;> simp at h <;> try simp
  next => exact Nat.lt_of_lt_of_le h le
  next => exact Nat.lt_of_lt_of_le h le
  next => exact ⟨Nat.lt_of_lt_of_le h.left le, Nat.lt_of_lt_of_le h.right le⟩
  next => exact Nat.lt_of_lt_of_le h le

end NFA

/--
  The NFA consists an array of nodes and a designated start node.

  The transition relation and accept nodes are embedded in the nodes themselves.
-/
structure NFA where
  nodes : Array NFA.Node
  start : Fin nodes.size
  inBounds : ∀ i : Fin nodes.size, nodes[i.val].inBounds nodes.size
deriving Repr

instance : ToString NFA where
  toString nfa := reprStr nfa

namespace NFA

def done : NFA :=
  let nodes := #[NFA.Node.done]
  let start := ⟨0, by decide⟩
  have inBounds := by
    intro i
    match i with
    | ⟨0, isLt⟩ => rfl
    | ⟨i + 1, isLt⟩ => contradiction
  ⟨nodes, start, inBounds⟩

def get (nfa : NFA) (i : Nat) (h : i < nfa.nodes.size) : NFA.Node :=
  nfa.nodes[i]

instance : GetElem NFA Nat NFA.Node (fun nfa i => i < nfa.nodes.size) where
  getElem := get

theorem get_eq_nodes_get (nfa : NFA) (i : Nat) (h : i < nfa.nodes.size) :
  nfa[i] = nfa.nodes[i] := rfl

theorem zero_lt_size {nfa : NFA} : 0 < nfa.nodes.size := by
  apply Nat.zero_lt_of_ne_zero
  intro h
  exact (h ▸ nfa.start).elim0

theorem inBoundsType (nfa : NFA) (i : Fin nfa.nodes.size) : nfa[i].InboundsType nfa.nodes.size := by
  rw [←Node.inBounds_iff]
  exact nfa.inBounds i

theorem inBoundsType' (nfa : NFA) (i : Fin nfa.nodes.size) (eq : nfa[i] = n) : n.InboundsType nfa.nodes.size :=
  eq ▸ nfa.inBoundsType i

end NFA
