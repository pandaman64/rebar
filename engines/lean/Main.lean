import Regex

set_option autoImplicit false

structure Klv where
  key : String
  -- not supporting arbitrary bytes
  val : String
deriving Inhabited, Repr

def parseKlvOne (data : ByteArray) (start : Nat) : Option (Klv × Nat) := do
  let colon : UInt8 := 0x3A -- :
  let newLine : UInt8 := 0x0A -- \n
  let keyEnd <- data.findIdx? (start := start) (· == colon)
  let lengthEnd <- data.findIdx? (start := keyEnd + 1) (· == colon)

  let key <- String.fromUTF8? (data.extract start keyEnd)
  let len <- String.toNat? (<- String.fromUTF8? (data.extract (keyEnd + 1) lengthEnd))

  let valEnd := lengthEnd + len + 1
  if data[valEnd]? != newLine then
    none
  let val <- String.fromUTF8? (data.extract (lengthEnd + 1) valEnd)

  return ({ key, val }, valEnd + 1)

def parseKlv (data : ByteArray) : Array Klv := Id.run do
  let mut start := 0
  let mut result := #[]
  while start < data.size do
    match parseKlvOne data start with
    | some (klv, next) =>
      result := result.push klv
      start := next
    | none => break
  return result

partial def IO.FS.Stream.readBinToEnd (stream : IO.FS.Stream) : IO ByteArray := do
  let rec loop (acc : ByteArray) : IO ByteArray := do
    let buf ← stream.read 4096
    if buf.isEmpty then
      return acc
    else
      loop (acc ++ buf)
  loop ByteArray.empty

def Option.okOr {α ε} (self : Option α) (err : Unit → ε) : Except ε α :=
  match self with
  | some a => Except.ok a
  | none => Except.error (err ())

structure Config where
  name : String
  model : String
  pattern : String
  regex : Regex
  caseInsensitive : Bool
  unicode : Bool
  haystack : String
  maxIters : Nat
  maxWarmupIters : Nat
  maxTime : Nat
  maxWarmupTime : Nat
deriving Repr

instance : ToString Config where
  toString c := reprStr c

def parseConfig (data : ByteArray) : Except String Config := do
  let mut start := 0
  let mut name := none
  let mut model := none
  let mut pattern := none
  let mut caseInsensitive := false
  let mut unicode := false
  let mut haystack := none
  let mut maxIters := 0
  let mut maxWarmupIters := 0
  let mut maxTime := 0
  let mut maxWarmupTime := 0

  while start < data.size do
    let (klv, next) ← (parseKlvOne data start).okOr (fun _ => "Failed to parse KLV")
    match klv.key with
    | "name" => name := some klv.val
    | "model" => model := some klv.val
    | "pattern" => pattern := some klv.val
    | "case-insensitive" => caseInsensitive := klv.val == "true"
    | "unicode" => unicode := klv.val == "true"
    | "haystack" => haystack := some klv.val
    | "max-iters" => maxIters := klv.val.toNat!
    | "max-warmup-iters" => maxWarmupIters := klv.val.toNat!
    | "max-time" => maxTime := klv.val.toNat!
    | "max-warmup-time" => maxWarmupTime := klv.val.toNat!
    | _ => throw s!"Unknown key: {klv.key}"
    start := next

  let regex ← Regex.parse pattern.get! |>.mapError (toString ·)

  return {
    name := name.get!,
    model := model.get!,
    pattern := pattern.get!,
    regex := regex,
    caseInsensitive := caseInsensitive,
    unicode := unicode,
    haystack := haystack.get!,
    maxIters := maxIters,
    maxWarmupIters := maxWarmupIters,
    maxTime := maxTime,
    maxWarmupTime := maxWarmupTime
  }

structure Sample where
  count : Nat
  duration : Nat
deriving Inhabited, Repr

instance : ToString Sample where
  toString s := reprStr s

def runBenchmarks {α : Type} (config : Config) (action : IO α) (count : α → Nat) : IO (Array Sample) := do
  let mut warmupStart ← IO.monoNanosNow
  for _ in [0:config.maxWarmupIters] do
    let _ ← action
    if (← IO.monoNanosNow) - warmupStart > config.maxWarmupTime then
      break

  let mut samples := #[]
  let runStart ← IO.monoNanosNow
  for _ in [0:config.maxIters] do
    let benchStart ← IO.monoNanosNow
    let result ← action
    let elapsed := (← IO.monoNanosNow) - benchStart
    samples := samples.push { count := count result, duration := elapsed }

    if (← IO.monoNanosNow) - runStart > config.maxTime then
      break

  return samples

def Regex.CapturedGroups.countGroups (groups : Regex.CapturedGroups) : Nat :=
  go groups 0 0
where
  go (groups : Regex.CapturedGroups) (i : Nat) (count : Nat) : Nat :=
    if i ≥ groups.buffer.size / 2 then
      count
    else
      match groups.get i with
      | some _ => go groups (i + 1) (count + 1)
      | none => go groups (i + 1) count
  termination_by groups.buffer.size / 2 - i

@[noinline]
def runCompile (config : Config) : IO Regex :=
  pure (Regex.parse! config.pattern)

def modelCompile (config : Config) : IO (Array Sample) :=
  runBenchmarks config (runCompile config) (fun r => (r.findAll config.haystack).size)

@[noinline]
def runFindAll (config : Config) : IO (Array (String.Pos × String.Pos)) :=
  pure $ (config.regex.findAll config.haystack).map fun s => (s.startPos, s.stopPos)

def modelCount (config : Config) : IO (Array Sample) := do
  runBenchmarks config (runFindAll config) (·.size)

def modelCountSpans (config : Config) : IO (Array Sample) :=
  runBenchmarks config (runFindAll config) (·.foldl (init := 0) (fun acc (s, e) => acc + (e - s).byteIdx))

@[noinline]
def runCaptureAll (config : Config) : IO (Array Regex.CapturedGroups) :=
  pure (config.regex.captureAll config.haystack)

def modelCountCaptures (config : Config) : IO (Array Sample) :=
  runBenchmarks config (runCaptureAll config) (·.foldl (init := 0) (fun acc groups => acc + groups.countGroups))

@[noinline]
def runGrep (config : Config) : IO Nat := do
  let lines := config.haystack.splitOn "\n"
  let mut count := 0
  for line in lines do
    let line := if line.endsWith "\r" then line.dropRight 1 else line
    if (config.regex.find line).isSome then
      count := count + 1
  return count

def modelGrep (config : Config) : IO (Array Sample) :=
  runBenchmarks config (runGrep config) id

@[noinline]
def runGrepCaptures (config : Config) : IO Nat := do
  let lines := config.haystack.splitOn "\n"
  let mut totalCount := 0
  for line in lines do
    let line := if line.endsWith "\r" then line.dropRight 1 else line
    let groups := config.regex.captureAll line
    for group in groups do
      totalCount := totalCount + group.countGroups
  return totalCount

def modelGrepCaptures (config : Config) : IO (Array Sample) :=
  runBenchmarks config (runGrepCaptures config) id

def main (args : List String) : IO Unit := do
  if args.contains "--version" then
    IO.println "v4.20.0"
    return

  let stdin ← IO.getStdin
  let input ← stdin.readBinToEnd
  let config ← match parseConfig input with
    | Except.ok c => pure c
    | Except.error e => throw (IO.userError e)

  let samples ← match config.model with
  | "compile" => modelCompile config
  | "count" => modelCount config
  | "count-spans" => modelCountSpans config
  | "count-captures" => modelCountCaptures config
  | "grep" => modelGrep config
  | "grep-captures" => modelGrepCaptures config
  | _ => throw (IO.userError s!"Unknown model: {config.model}")

  for sample in samples do
    IO.println s!"{sample.duration},{sample.count}"
