// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./Token.sol";

contract GameToken is Token {
    mapping(address => uint256) private _lastActionTime;
    mapping(address => uint256) private _balances;
    uint256 private constant COOLDOWN_PERIOD = 1 days;

    constructor() Token("GameToken", "GAME") {}

    function mint(address player, uint256 amount) public {
        require(isAdmin(msg.sender), "Only admin can mint");
        require(_balances[player] >= amount, "Insufficient balance");
        _mint(player, amount);
    }

    function burnFromPlayer(address player, uint256 amount) public {
        require(isAdmin(msg.sender), "Only admin can burn");
        require(_balances[player] >= amount, "Insufficient balance");
        _burn(player, amount);
    }

    function rewardPlayer(address player, uint256 amount) public {
        require(isAdmin(msg.sender), "Only admin can reward");
        require(canReceiveReward(player), "Player in cooldown");
        _reward(player, amount);
    }

    function _reward(address player, uint256 amount) private {
        _updateCooldown(player);
        _mint(player, amount);
        emit PlayerRewarded(player, amount);
    }

    function _burn(address account, uint256 amount) private {
        _transfer(account, address(0), amount);
    }

    function _updateCooldown(address player) private {
        _lastActionTime[player] = block.timestamp;
    }

    function canReceiveReward(address player) public view returns (bool) {
        return block.timestamp >= _lastActionTime[player] + COOLDOWN_PERIOD;
    }

    function isAdmin(address account) private pure returns (bool) {
        // Simplified admin check for example
        return account == address(0x123);
    }

    event PlayerRewarded(address indexed player, uint256 amount);
}
