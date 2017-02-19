pragma solidity ^0.4.3;

// External interface
contract PreimageManager {
    function submitPreimage(bytes32 x) {}
    function revealedBefore(bytes32 h, uint T) returns(bool) {}
}

// Note: Initial version does NOT support concurrent conditional payments!

contract SpriteChannel {

    // Blocks for grace period
    uint constant DELTA = 10; 

    // Events
    event EventInit();
    event EventUpdate(int r);
    event LogBytes32(bytes32 b);
    event EventPending(uint T1, uint T2);

    // Utility functions
    modifier after_ (uint T) { if (T > 0 && block.number >= T) _; else throw; }
    modifier before(uint T) { if (T == 0 || block.number <  T) _; else throw; }
    modifier onlyplayers { if (playermap[msg.sender] > 0) _; else throw; }
    function assert(bool b) internal { if (!b) throw; }
    function max(uint a, uint b) internal returns(uint) { if (a>b) return a; else return b; }
    function min(uint a, uint b) internal returns(uint) { if (a<b) return a; else return b; }
    function verifySignature(address pub, bytes32 h, uint8 v, bytes32 r, bytes32 s) {
        if (pub != ecrecover(h,v,r,s)) throw;
    }

    ///////////////////////////////
    // State channel data
    ///////////////////////////////
    int bestRound = -1;
    enum Status { OK, PENDING }
    Status public status;
    uint deadline;

    // Constant (set in constructor)
    address[2] public players;
    mapping (address => uint) playermap;
    PreimageManager pm;

    /////////////////////////////////////
    // Sprite - Application specific data 
    ////////////////////////////////////
    
    // State channel states
    int [2] public credits;
    uint[2] public withdrawals;

    // Conditional payment
    // NOTE: for simplicity, only one conditional payment supported, L to R
    bytes32 public hash;
    uint public expiry;
    uint public amount;

    // Externally affected states
    uint[2] public deposits; // Monotonic, only incremented by deposit() function
    uint[2] public withdrawn; // Monotonic, only incremented by withdraw() function

    function sha3int(int r) constant returns(bytes32) {
	return sha3(r);
    }

    function SpriteChannel(PreimageManager _pm, address[2] _players) {
	pm = _pm;
        for (uint i = 0; i < 2; i++) {
            players[i] = _players[i];
            playermap[_players[i]] = i + 1;
        }
        EventInit();
    }

    // Increment on new deposit
    function deposit() payable onlyplayers {
	deposits[playermap[msg.sender]-1] += msg.value;
    }

    // Increment on withdrawal
    function withdraw() onlyplayers {
	uint i = playermap[msg.sender]-1;
	uint toWithdraw = withdrawals[i] - withdrawn[i];
	withdrawn[i] = withdrawals[i];
	assert(msg.sender.send(toWithdraw));
    }

    // State channel update function
    function update(uint[3] sig, int r, int[2] _credits, uint[2] _withdrawals,
		    bytes32 _hash, uint _expiry, uint _amount)
    onlyplayers {
	
        // Only update to states with larger round number
        if (r <= bestRound) return;

        // Check the signature of the other party
	uint i = (3 - playermap[msg.sender]) - 1;
        var _h = sha3(r, _credits, _withdrawals, _hash, _expiry, _amount);
	var V =  uint8 (sig[0]);
	var R = bytes32(sig[1]);
	var S = bytes32(sig[2]);
	verifySignature(players[i], _h, V, R, S);

	// Update the state
	credits[0] = _credits[0];
	credits[1] = _credits[1];
	withdrawals[0] = _withdrawals[0];
	withdrawals[1] = _withdrawals[1];
	amount = _amount;
	hash = _hash;
	expiry = _expiry;
	bestRound = r;
        EventUpdate(r);
    }

    // Causes a timeout for the finalize time
    function trigger() onlyplayers {
	assert( status == Status.OK );
	status = Status.PENDING;
	deadline = block.number + DELTA; // Set the deadline for collecting inputs or updates
        EventPending(block.number, deadline);
    }
    
    function finalize() {
	assert( status == Status.PENDING );
	assert( block.number > deadline );

	// Finalize is safe to call multiple times
	// If "trigger" occurs before a hashlock expires, finalize will need to be called again

	if (amount > 0 && block.number > expiry) {
	    // Completes on-chain
	    if (pm.revealedBefore(hash, expiry))
		withdrawals[1] += amount;
	    // Cancels off-chain
	    else
		withdrawals[0] += amount;
	    amount = 0;
	    hash = 0;
	    expiry = 0;
	}

	// Withdraw the maximum amount of money
	withdrawals[0] += uint(int(deposits[0]) + credits[0]);
	withdrawals[1] += uint(int(deposits[1]) + credits[1]);
	credits[0] = -int(deposits[0]);
	credits[1] = -int(deposits[1]);
    }
}
